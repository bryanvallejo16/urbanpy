import pandas as pd
import geopandas as gpd
import osmnx as ox
from h3 import h3
from tqdm import tqdm
from shapely.geometry import Point, Polygon

__all__ = [
    'merge_geom_downloads',
    'filter_population',
    'remove_features',
    'gen_hexagons',
    'merge_shape_hex',
    'osmnx_graph_download',
]

def merge_geom_downloads(gdfs):
    '''
    Merge several GeoDataFrames from OSM download_osm

    Parameters
    ----------

    dfs : array_like
             Array of GeoDataFrames to merge

    Returns
    -------

    concat : GeoDataFrame
                Output from concatenation and unary union of geometries, providing
                a single geometry database for the city

    Examples
    --------

    >>> lima = download_osm(2, "Lima, Peru")
    >>> callao = download_osm(1, "Callao, Peru")
    >>> lima = merge_geom_downloads([lima, callao])
    >>> lima.head()
    geometry
    MULTIPOLYGON (((-76.80277 -12.47562, -76.80261...)))

    '''

    concat = gpd.GeoDataFrame(geometry=[pd.concat(gdfs).unary_union])
    return concat

def filter_population(pop_df, polygon_gdf):
    '''
    Filter an HDX database download to the polygon bounds

    Parameters
    ----------

    pop_df : DataFrame
                Result from download_hdx

    polygon_gdf : GeoDataFrame
                     Result from download_osm or merge_geom_downloads

    Returns
    -------

    filtered_points_gdf : GeoDataFrame
                         Population DataFrame filtered to polygon bounds

    Examples
    --------

    >>> lima = download_osm(2, 'Lima, Peru')
    >>> callao = download_osm(1, 'Callao, Peru')
    >>> lima = merge_geom_downloads([lima, callao])
    >>> pop = pop_lima = download_hdx_population_data("4e74db39-87f1-4383-9255-eaf8ebceb0c9/resource/317f1c39-8417-4bde-a076-99bd37feefce/download/population_per_2018-10-01.csv.zip")
    >>> filter_population(pop, lima)
    latitude   | longitude  | population_2015 | population_2020 | geometry
    -12.519861 | -76.774583 | 2.633668        | 2.644757        | POINT (-76.77458 -12.51986)
    -12.519861 | -76.745972 | 2.633668        | 2.644757        | POINT (-76.74597 -12.51986)
    -12.519861 | -76.745694 | 2.633668        | 2.644757        | POINT (-76.74569 -12.51986)
    -12.519861 | -76.742639 | 2.633668        | 2.644757        | POINT (-76.74264 -12.51986)
    -12.519861 | -76.741250 | 2.633668        | 2.644757        | POINT (-76.74125 -12.51986)

    '''

    minx, miny, maxx, maxy = polygon_gdf.geometry.total_bounds
    limits_filter = pop_df['longitude'].between(minx, maxx) & pop_df['latitude'].between(miny, maxy)
    filtered_points = pop_df[limits_filter]

    geometry_ = gpd.points_from_xy(filtered_points['longitude'], filtered_points['latitude'])
    filtered_points_gdf = gpd.GeoDataFrame(filtered_points, geometry=geometry_, crs='EPSG:4326')

    return filtered_points_gdf

def remove_features(gdf, bounds):
    '''
    Remove a set of features based on bounds

    Parameters
    ----------

    gdf : GeoDataFrame
             Input GeoDataFrame containing the point features filtered with filter_population

    bounds : array_like
                Array input following [miny, maxy, minx, maxx] for filtering


    Returns
    -------

    gdf : GeoDataFrame
             Input DataFrame but without the desired features

    Examples
    --------

    >>> lima = filter_population(pop_lima, poly_lima)
    >>> removed = remove_features(lima, [-12.2,-12, -77.2,-77.17]) #Remove San Lorenzo Island
    >>> print(lima.shape, removed.shape)
    (348434, 4) (348427, 4)

    '''
    miny, maxy, minx, maxx = bounds
    filter = gdf['latitude'].between(miny,maxy) & gdf['longitude'].between(minx,maxx)
    drop_ix = gdf[filter].index

    return gdf.drop(drop_ix)

def gen_hexagons(resolution, city):
    '''
    Converts an input multipolygon layer to H3 hexagons given a resolution.

    Parameters
    ----------

    resolution : int, 0:15
                    Hexagon resolution, higher values create smaller hexagons.

    city : GeoDataFrame
              Input city polygons to transform into hexagons.

    Returns
    -------

    city_hexagons : GeoDataFrame
                       Hexagon geometry GeoDataFrame (hex_id, geom).

    city_centroids : GeoDataFrame
                        Hexagon centroids for the specified city (hex_id, geom).

    Examples
    --------

    >>> lima = filter_population(pop_lima, poly_lima)
    >>> lima_hex = gen_hexagons(8, lima)
    0	            | geometry
    888e620e41fffff | POLYGON ((-76.80007 -12.46917, -76.80439 -12.4...))
    888e62c809fffff | POLYGON ((-77.22539 -12.08663, -77.22971 -12.0...))
    888e62c851fffff | POLYGON ((-77.20708 -12.08484, -77.21140 -12.0...))
    888e62c841fffff | POLYGON ((-77.22689 -12.07104, -77.23122 -12.0...))
    888e62c847fffff | POLYGON ((-77.23072 -12.07929, -77.23504 -12.0...))
    0	            | geometry
    888e620e41fffff | POINT (-76.79956 -12.47436)
    888e62c809fffff | POINT (-77.22488 -12.09183)
    888e62c851fffff | POINT (-77.20658 -12.09004)
    888e62c841fffff | POINT (-77.22639 -12.07624)
    888e62c847fffff | POINT (-77.23021 -12.08448)

    '''

    # Polyfill the city boundaries
    h3_centroids = list()
    h3_polygons = list()
    h3_indexes = list()

    # Get every polygon in Multipolygon shape
    city_poly = city.explode().reset_index(drop=True)

    for ix, geo in city_poly.iterrows():
        hexagons = h3.polyfill(geo['geometry'].__geo_interface__, res=resolution, \
                                    geo_json_conformant=True)
        for hexagon in hexagons:
            centroid_lat, centroid_lon = h3.h3_to_geo(hexagon) # format as x,y (lon, lat)
            h3_centroids.append(Point(centroid_lon, centroid_lat))

            h3_geo_boundary = h3.h3_to_geo_boundary(hexagon)
            [bound.reverse() for bound in h3_geo_boundary] # format as x,y (lon, lat)
            h3_polygons.append(Polygon(h3_geo_boundary))

            h3_indexes.append(hexagon)

    # Create hexagon dataframe
    city_hexagons = gpd.GeoDataFrame(h3_indexes, geometry=h3_polygons).drop_duplicates()
    city_hexagons.crs = 'EPSG:4326'
    city_centroids = gpd.GeoDataFrame(h3_indexes, geometry=h3_centroids).drop_duplicates()
    city_centroids.crs = 'EPSG:4326'

    return city_hexagons, city_centroids

def merge_shape_hex(hex, shape, how, op, agg):
    '''
    Merges a H3 hexagon GeoDataFrame with a Point GeoDataFrame and aggregates the
    point gdf data.

    Parameters
    ----------

    hex : GeoDataFrame
             Input GeoDataFrame containing hexagon geometries

    shape : GeoDataFrame
                Input GeoDataFrame containing points and features to be aggregated

    how : str. One of {'inner', 'left', 'right'}. Determines how to merge data.
             'left' uses keys from left and only retains geometry from left
             'right' uses keys from right and only retains geometry from right
             'inner': use intersection of keys from both dfs; retain only left geometry column

    op : str. One of {'intersects', 'contains', 'within'}. Determines how
                 geometries are queried for merging.

    agg : dict. A dictionary with column names as keys and values as aggregation
             operations. The aggregation must be one of {'sum', 'min', 'max'}.

    Returns
    -------

    hex : GeoDataFrame
                   Result of a spatial join within hex and points. All features are aggregated
                   based on the input parameters

    Examples
    --------

    >>> lima = download_osm(2, 'Lima, Peru')
    >>> pop_lima = download_hdx(...)
    >>> pop_df = filter_population(pop_lima, lima)
    >>> hex = gen_hexagons(8, lima)
    >>> merge_point_hex(hex, pop_df, 'inner', 'within', {'population_2020':'sum'})
    0               | geometry                                          | population_2020
    888e628d8bfffff | POLYGON ((-76.66002 -12.20371, -76.66433 -12.2... | NaN
    888e62c5ddfffff | POLYGON ((-76.94564 -12.16138, -76.94996 -12.1... | 14528.039097
    888e62132bfffff | POLYGON ((-76.84736 -12.17523, -76.85167 -12.1... | 608.312696
    888e628debfffff | POLYGON ((-76.67982 -12.18998, -76.68413 -12.1... | NaN
    888e6299b3fffff | POLYGON ((-76.78876 -11.97286, -76.79307 -11.9... | 3225.658803

    '''
    joined = gpd.sjoin(shape, hex, how=how, op=op)

    #Uses index right based on the order of points and hex. Right takes hex index
    hex_merge = joined.groupby('index_right').agg(agg)

    #Avoid SpecificationError by copying the DataFrame
    ret_hex = hex.copy()

    for key in agg.keys():
        ret_hex.loc[hex_merge.index, key] = hex_merge[key].values

    return ret_hex

def osmnx_graph_download(gdf, net_type, basic_stats, extended_stats, connectivity=False, anc=False, ecc=False, bc=False, cc=False):
    '''
    Apply osmnx's graph from polygon to query a city's street network within a geometry.

    Parameters
    ----------

    gdf : GeoDataFrame
             GeoDataFrame with geometries to download graphs contained within them.

    basic_stats : list
                     List of basic stats to compute from downloaded graph

    extended_stats : list
                        List of extended stats to compute from graph

    connectivity : bool. Default False.
                      Compute node and edge connectivity

    anc : bool. Default False.
             Compute avg node connectivity
    ecc : bool. Default False.
             Compute shortest paths, eccentricity and topological metric
    bc : bool. Default False.
             Compute node betweeness centrality
    cc : bool. Default False.
             Compute node closeness centrality

    For more detail about these parameters, see https://osmnx.readthedocs.io/en/stable/osmnx.html#module-osmnx.stats

    Returns
    -------

    gdf : Input GeoDataFrame with updated columns containing the selected metrics

    '''

    #May be a lengthy download depending on the amount of features
    for index, row in tqdm(gdf.iterrows()):
        try:
            graph = ox.graph_from_polygon(row['geometry'], net_type)
            b_stats = ox.basic_stats(graph)
            ext_stats = ox.extended_stats(graph, connectivity, anc, ecc, bc, cc)

            for stat in basic_stats:
                gdf.loc[index, stat] = b_stats.get(stat)
            for stat in extended_stats:
                gdf.loc[index, stat] = ext_stats.get(stat)
        except Exception as err:
                print(f'On record {index}: ', err)
                pass
    return gdf