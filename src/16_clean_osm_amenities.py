import geopandas as gpd
import pandas as pd
from shapely import Geometry, from_wkt


def prepare(path: str) -> gpd.GeoDataFrame:
    amenity_types = ["amenity", "leisure", "office", "shop", "tourism"]
    result = gpd.GeoDataFrame()
    for amenity_type in amenity_types:
        gdf = gpd.read_file(f"{path}/{amenity_type}.geojson", engine="pyogrio")
        gdf.rename(
            {"@id": "osm_id", "@type": "osm_type", amenity_type: "amenity_subtype"},
            axis=1,
            inplace=True,
        )
        gdf["amenity_type"] = amenity_type
        gdf = gdf[
            gdf["geometry"].type.isin(["Point", "Polygon", "MultiPolygon"])
        ].copy()
        gdf["category"] = gdf["amenity_type"] + ":" + gdf["amenity_subtype"]
        gdf = extract_polygons(gdf)
        gdf["geometry_type"] = gdf.geometry.type

        gdf.to_csv(f"{path}/{amenity_type}.wkt.csv", index=False)
        gdf[keep].to_csv(f"{path}/{amenity_type}_cleaned.wkt.csv", index=False)
        result = pd.concat([result, gdf])
    return result


def multipolygon_to_polygon(g: Geometry) -> Geometry:
    """
    Extract polygon from multipolygon if only one polygon is in the set.

    :param g: shapely.Geometry

    :return: shapely.geometry

    >>> from shapely.geometry import Point, Polygon, MultiPolygon
    >>> mp = MultiPolygon([Polygon([Point(1, 7), Point(4, 2), Point(6, 3)])])
    >>> multipolygon_to_polygon(mp)
    <POLYGON ((1 7, 4 2, 6 3, 1 7))>
    """
    if g.geom_type == "MultiPolygon" and len(g.geoms) == 1:
        return g.geoms[0]
    return g


def extract_polygons(x: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Extract polygon from multipolygon if only one polygon is in the set for\
    every row of a GeoDataFrame.

    >>> from shapely.geometry import Point, Polygon, MultiPolygon
    >>> mp = MultiPolygon([Polygon([Point(1, 7), Point(4, 2), Point(6, 3)])])
    >>> p = MultiPolygon([Polygon([Point(0, 0), Point(4, 0), Point(4, 3)])])
    >>> gdf = gpd.GeoDataFrame(geometry=[mp, p])
    >>> extract_polygons(gdf)
    ... # doctest: +NORMALIZE_WHITESPACE
                                                    geometry
    0  POLYGON ((1.00000 7.00000, 4.00000 2.00000, 6....
    1  POLYGON ((0.00000 0.00000, 4.00000 0.00000, 4....
    """
    y = x.copy()
    y["geometry"] = y["geometry"].apply(multipolygon_to_polygon)
    return y


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    argparser = argparse.ArgumentParser()
    argparser.add_argument("--area", type=str, help="area to process")
    argparser.add_argument(
        "--output", type=str, default="output", help="output directory"
    )
    opts = argparser.parse_args()

    keep = [
        "osm_id",
        "osm_type",
        "amenity_type",
        "amenity_subtype",
        "category",
        "name",
        "geometry_type",
        "geometry",
    ]
    Path(f"{opts.output}/{opts.area}/amenities").mkdir(parents=True, exist_ok=True)
    try:
        amenities = pd.read_csv(
            f"{opts.output}/{opts.area}/amenities/amenities.wkt.csv",
            engine="pyarrow",
        )
        amenities["geometry"] = amenities["geometry"].apply(from_wkt)
        amenities = gpd.GeoDataFrame(amenities, geometry="geometry", crs=4326)
    except FileNotFoundError:
        amenities = prepare(f"{opts.output}/{opts.area}/amenities")
        amenities[keep].to_csv(
            f"{opts.output}/{opts.area}/amenities/amenities_cleaned.wkt.csv",
            index=False,
        )
