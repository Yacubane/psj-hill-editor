zakopane : hills/zakopane_hs140/zakopane.svg hills/zakopane_hs140/build.json
	python3 psjhill_exporter/psjhill_exporter.py hills/zakopane_hs140/zakopane.svg -b hills/zakopane_hs140/build.json
planica : hills/planica_hs240/drawing.svg hills/planica_hs240/build.json
	python3 psjhill_exporter/psjhill_exporter.py hills/planica_hs240/drawing.svg -b hills/planica_hs240/build.json
userhill : user_hill/hill.svg user_hill/build.json
	python3 psjhill_exporter/psjhill_exporter.py user_hill/hill.svg -b user_hill/build.json
