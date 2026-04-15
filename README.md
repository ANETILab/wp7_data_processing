# data processing repository for DUT/COLINE/WP7

## Setup

The [`pyproject.toml`](pyproject.toml) document the required dependencies. It's suggested to use the [uv](https://docs.astral.sh/uv/) packaging tool. In this case, just issue the `uv sync` command to set up a virtual environment with all the necessary dependencies.

## Usage

### Repository structure

Open data, such as shapefiles extracted from OSM, are available in the `data/` folder, all the proprietary data are excluded.
The `config.yaml` in the root describes city-specific variables, such as paths for the mobility data.

Codes are in the `src/` folder, both Jupyter notebooks and scripts.

Outputs, that could be published are generated into the `output/` folder.

### Pipeline

The development and analysis codes are in Jupyter notebook formats, but parts of the pipeline that runs long can be found in scripts.
Notebooks may depend on the scripts.
For example, 05_detect_stops.ipynb was used to develop the stop detection part of the pipeline, but the detect_stops.py contains the functions.
detect_stops.py can also used to process the full data.

## Licensing

The file-level licensing information is described in the REUSE.toml accoding to the [REUSE convention](https://reuse.software/).
