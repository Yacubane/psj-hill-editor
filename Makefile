zakopane : hills/zakopane_hs140/zakopane.svg hills/zakopane_hs140/build.json output.zip
	python3 psjhill_exporter/psjhill_exporter.py hills/zakopane_hs140/zakopane.svg -b hills/zakopane_hs140/build.json
planica : hills/planica_hs240/drawing.svg hills/planica_hs240/build.json output.zip
	python3 psjhill_exporter/psjhill_exporter.py hills/planica_hs240/drawing.svg -b hills/planica_hs240/build.json