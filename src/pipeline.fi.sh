
#!/usr/bin/fish

uv run create_id_lookup.py --config ../config.budapest.yaml

uv run clean.py --config ../config.budapest.yaml

uv run detect_stops.py --config ../config.budapest.yaml --stop-detection-config 05_detect_stops_config_v2.yaml --pool 10
uv run detect_stops.py --config ../config.budapest.yaml --stop-detection-config 05_detect_stops_config_v1.yaml --pool 10

uv run detect_home.py --input /mnt/common-ssd/group-dirs/tkom-2026-project/pickwell/budapest/stops/v1 --output /mnt/common-ssd/group-dirs/tkom-2026-project/pickwell/budapest/homes/v1 --config 06_home_detection_config.yaml
uv run detect_home.py --input /mnt/common-ssd/group-dirs/tkom-2026-project/pickwell/budapest/stops/v2 --output /mnt/common-ssd/group-dirs/tkom-2026-project/pickwell/budapest/homes/v2 --config 06_home_detection_config.yaml

uv run build_hexagon_network.py --config ../config.budapest.yaml

uv run build_commuting_aware_visitation_network.py --config ../config.budapest.yaml --visitation-network-config 09_visitation_network_config_v1_freq.yaml
uv run build_commuting_aware_visitation_network.py --config ../config.budapest.yaml --visitation-network-config 09_visitation_network_config_v2_freq.yaml

uv run 10_repartition_stops.py --config ../config.budapest.yaml --stop-detection-variant v1
uv run 10_repartition_stops.py --config ../config.budapest.yaml --stop-detection-variant v2

uv run 06_howde.py 06_howde_config_v1.yaml
uv run 06_howde.py 06_howde_config.yaml

uv run 10_repartition_labeled_stops.py --config ../config.budapest.yaml --stop-detection-variant v1
uv run 10_repartition_labeled_stops.py --config ../config.budapest.yaml --stop-detection-variant v2
