"""
Author:      www.tropofy.com

Copyright 2015 Tropofy Pty Ltd, all rights reserved.

This source file is part of Tropofy and governed by the Tropofy terms of service
available at: http://www.tropofy.com/terms_of_service.html

This source file is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
or FITNESS FOR A PARTICULAR PURPOSE. See the license files for details.
"""

from sqlalchemy.types import Text, Float, Boolean
from sqlalchemy.schema import Column, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from simplekml import Kml, Style, IconStyle, Icon, LineStyle

from tropofy.app import AppWithDataSets, Step, StepGroup
from tropofy.widgets import ExecuteFunction, SimpleGrid, KMLMap
from tropofy.database.tropofy_orm import DataSetMixin


class Location(DataSetMixin):
    name = Column(Text, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    start = Column(Boolean, nullable=False, default=False)

    def __init__(self, name, latitude, longitude, start):
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.start = start

    @classmethod
    def get_table_args(cls):
        return (UniqueConstraint('data_set_id', 'name', name='_location_uc'),)


class Path(DataSetMixin):
    start_location_name = Column(Text, nullable=False)
    end_location_name = Column(Text, nullable=False)

    # The primaryjoin argument to relationship is only needed when there is ambiguity
    start_location = relationship(Location, primaryjoin="and_(Path.data_set_id==Location.data_set_id, Path.start_location_name==Location.name)")
    end_location = relationship(Location, primaryjoin="and_(Path.data_set_id==Location.data_set_id, Path.end_location_name==Location.name)")

    def __init__(self, start_location_name, end_location_name):
        self.start_location_name = start_location_name
        self.end_location_name = end_location_name

    @classmethod
    def get_table_args(cls):
        return (
            ForeignKeyConstraint(['start_location_name', 'data_set_id'], ['location.name', 'location.data_set_id'], ondelete='CASCADE', onupdate='CASCADE'),
            ForeignKeyConstraint(['end_location_name', 'data_set_id'], ['location.name', 'location.data_set_id'], ondelete='CASCADE', onupdate='CASCADE')
        )
		
class OutputPath(DataSetMixin):
    start_location_name = Column(Text, nullable=False)
    end_location_name = Column(Text, nullable=False)

    # The primaryjoin argument to relationship is only needed when there is ambiguity
    start_location = relationship(Location, primaryjoin="and_(OutputPath.data_set_id==Location.data_set_id, OutputPath.start_location_name==Location.name)")
    end_location = relationship(Location, primaryjoin="and_(OutputPath.data_set_id==Location.data_set_id, OutputPath.end_location_name==Location.name)")

    def __init__(self, start_location_name, end_location_name):
        self.start_location_name = start_location_name
        self.end_location_name = end_location_name

    @classmethod
    def get_table_args(cls):
        return (
            ForeignKeyConstraint(['start_location_name', 'data_set_id'], ['location.name', 'location.data_set_id'], ondelete='CASCADE', onupdate='CASCADE'),
            ForeignKeyConstraint(['end_location_name', 'data_set_id'], ['location.name', 'location.data_set_id'], ondelete='CASCADE', onupdate='CASCADE')
        )
		
class ExecuteLocalSolver(ExecuteFunction):
    def get_button_text(self, app_session):
        return "Solve"

    def execute_function(self, app_session):
		app_session.task_manager.send_progress_message("Deleting old results")
		app_session.data_set.query(OutputPath).delete()

		outputpaths = []
		
		startLocation = app_session.data_set.query(Location).filter_by(start=True)
		
		if startLocation.count() != 1:
			app_session.task_manager.send_progress_message("Exactly 1 location must be the start point.")
		else :
			result = bfs(app_session, startLocation.one().name)
			
			for i in range(0, len(result.visited)):
				paths = app_session.data_set.query(Path).filter_by(start_location_name=result.visited[i]).filter_by(end_location_name=result.visited[(i+1)%len(result.visited)])
				for path in paths:
					outputpaths.append(OutputPath(path.start_location_name, path.end_location_name))
					
				paths = app_session.data_set.query(Path).filter_by(end_location_name=result.visited[i]).filter_by(start_location_name=result.visited[(i+1)%len(result.visited)])
				for path in paths:
					outputpaths.append(OutputPath(path.start_location_name, path.end_location_name))
			
			app_session.data_set.add_all(outputpaths)
			
			app_session.task_manager.send_progress_message("Finished")

# An object representing a potential journey so far
class Journey():	
	visited = []
	current = ''
	
	def __init__(self, start, visited):
		self.current = start
		self.visited = visited
	
# Perform a Breadth-first search for the path with most non-repeated nodes that returns to the beginning
def bfs(app_session, start):
    bestsofar = Journey(start, [])
    queue = [bestsofar]
	
    while queue:
		vertex = queue.pop(0)
		
		results = app_session.data_set.query(Path).filter_by(start_location_name=vertex.current)
		for result in results:
			if result.end_location_name not in vertex.visited:
				nextstep = Journey(result.end_location_name, vertex.visited[:])
				nextstep.visited.append(vertex.current)
				queue.append(nextstep)
			
			# Because we are using Breadth-first search, any new result will be of equal or greater length
			if result.end_location_name == start:
				bestsofar = Journey(result.end_location_name, vertex.visited[:]) 
				bestsofar.visited.append(vertex.current)

		results = app_session.data_set.query(Path).filter_by(end_location_name=vertex.current)
		for result in results:
			if result.start_location_name not in vertex.visited:
				nextstep = Journey(result.start_location_name, vertex.visited[:])
				nextstep.visited.append(vertex.current)
				queue.append(nextstep)
			
			# Because we are using Breadth-first search, any new result will be of equal or greater length
			if result.start_location_name == start:
				bestsofar = Journey(result.start_location_name, vertex.visited[:]) 
				bestsofar.visited.append(vertex.current)
				
    return bestsofar		

class MyKMLMap(KMLMap):
    def get_kml(self, app_session):

        kml = Kml()

        def LongLat(l):
            return (l.longitude, l.latitude)

        mylocstyle = Style(iconstyle=IconStyle(scale=0.8, icon=Icon(href='https://maps.google.com/mapfiles/kml/paddle/blu-circle-lv.png')))
        LocsFolder = kml.newfolder(name="Locations")
        locations =  app_session.data_set.query(Location).all()
        if len(locations) < 100:
            for p in [LocsFolder.newpoint(name=loc.name, coords=[LongLat(loc)]) for loc in locations]:
                p.style = mylocstyle

        mylinestyle = Style(linestyle=LineStyle(color='FF0000FF', width=4))
        PathsFolder = kml.newfolder(name="Paths")

        paths = app_session.data_set.query(Path).all()
        if len(paths) < 100:
            for path in [PathsFolder.newlinestring(name='path', coords=[LongLat(l.start_location), LongLat(l.end_location)]) for l in paths]:
                path.style = mylinestyle
			
				
        mylinestyle = Style(linestyle=LineStyle(color='FF00FF00', width=4))
        PathsFolder = kml.newfolder(name="Paths")

        paths = app_session.data_set.query(OutputPath).all()
        if len(paths) < 100:
            for path in [PathsFolder.newlinestring(name='path', coords=[LongLat(l.start_location), LongLat(l.end_location)]) for l in paths]:
                path.style = mylinestyle

        return kml.kml()


class MyKMLGeneratorApp(AppWithDataSets):

    def get_name(self):
        return "Tourist"

    def get_examples(self):
        return {"Demo data for Europe": self.load_example_data_for_europe}

    def get_gui(self):
        step_group1 = StepGroup(name='Enter your data')
        step_group1.add_step(Step(name='Enter your locations', widgets=[SimpleGrid(Location)]))
        step_group1.add_step(Step(name='Enter your paths', widgets=[SimpleGrid(Path)]))

        step_group2 = StepGroup(name='Solve')
        step_group2.add_step(Step(name='Solve', widgets=[ExecuteLocalSolver()]))

        step_group3 = StepGroup(name='View Results')
        step_group3.add_step(Step(name='View your Results', widgets=[MyKMLMap()]))

        return [step_group1, step_group2, step_group3]

    @staticmethod
    def load_example_data_for_europe(app_session):
        locs = []
		
        locs.append(Location("London", 51.510826, -0.119476, True))
        locs.append(Location("Paris", 48.860649, 2.351074, False))
        locs.append(Location("Brussels", 50.8518, 4.375305, False))
        locs.append(Location("Amsterdam", 52.38042, 4.894409, False))
        locs.append(Location("Berlin", 52.519929, 13.395081, False))
        locs.append(Location("Copenhagen", 55.713187, 12.568359, False))
        locs.append(Location("Stockholm", 59.320579, 18.149414, False))
        locs.append(Location("Helsinki", 60.190012, 24.938965, False))
        locs.append(Location("Prague", 50.070362, 14.39209, False))
        locs.append(Location("Warsaw", 52.253027, 21.049805, False))
        locs.append(Location("Minsk", 53.884107, 27.553711, False))
        locs.append(Location("Vilnius", 54.692091, 25.268555, False))
        locs.append(Location("Riga", 56.959578, 24.11499, False))
        locs.append(Location("Moscow", 55.752188, 37.625427, False))
        locs.append(Location("Oslo", 59.94263, 10.722656, False))
        app_session.data_set.add_all(locs)
        MyKMLGeneratorApp.load_example_paths(locs, app_session.data_set)

    @staticmethod
    def load_example_paths(locations, data_set):
        paths = []
        paths.append(Path(locations[0].name, locations[1].name))
        paths.append(Path(locations[0].name, locations[2].name))
        paths.append(Path(locations[0].name, locations[14].name))
        paths.append(Path(locations[3].name, locations[5].name))
        paths.append(Path(locations[5].name, locations[6].name))
        paths.append(Path(locations[5].name, locations[14].name))
        paths.append(Path(locations[13].name, locations[10].name))
        paths.append(Path(locations[13].name, locations[12].name))
        paths.append(Path(locations[13].name, locations[6].name))
        paths.append(Path(locations[11].name, locations[5].name))
        paths.append(Path(locations[9].name, locations[5].name))
        paths.append(Path(locations[9].name, locations[11].name))
        paths.append(Path(locations[8].name, locations[4].name))
        paths.append(Path(locations[8].name, locations[3].name))
        paths.append(Path(locations[8].name, locations[9].name))
        paths.append(Path(locations[8].name, locations[6].name))
        paths.append(Path(locations[2].name, locations[4].name))
        paths.append(Path(locations[7].name, locations[13].name))
        paths.append(Path(locations[7].name, locations[10].name))
        paths.append(Path(locations[1].name, locations[8].name))
        paths.append(Path(locations[7].name, locations[12].name))
        paths.append(Path(locations[1].name, locations[2].name))
        data_set.add_all(paths)

    def get_icon_url(self):
        return 'https://s3-ap-southeast-2.amazonaws.com/tropofy.com/static/css/img/tropofy_example_app_icons/kml_generation.png'
    
    def get_home_page_content(self):
        return {'content_app_name_header': '''
                <div>
                <span style="vertical-align: middle;">Tourist</span>
                <img src="https://s3-ap-southeast-2.amazonaws.com/tropofy.com/static/css/img/tropofy_example_app_icons/kml_generation.png" alt="main logo" style="width:15%">
                </div>''',
                'content_single_column_app_description': '',
                'content_double_column_app_description_1': '',
                'content_double_column_app_description_2': '',
                'content_row_2_col_1_header': '',
                'content_row_2_col_1_content': '',
                'content_row_2_col_2_header': '',
                'content_row_2_col_2_content': '',
                'content_row_2_col_3_header': '',
                'content_row_2_col_3_content': '',
                'content_row_3_col_1_header': '',
                'content_row_3_col_1_content': '',
                'content_row_3_col_2_header': '',
                'content_row_3_col_2_content': '',
                'content_row_4_col_1_header': '',
                'content_row_4_col_1_content': '''
                This app was created using the <a href="http://www.tropofy.com" target="_blank">Tropofy platform</a>.
                '''
            }