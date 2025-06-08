significant_features = ['price_object',
 'rooms_count',
 'area',
 'area_kitchen',
 'area_live',
 'area_live_ratio',
 'area_kitchen_ratio',
 'area_per_renovation',
 'year_buld',
 'h3_categorical',
 'floors_count',
 'distance_to_center',
 'distance_to_subway']

import numpy as np
import pandas as pd
import psycopg2
import warnings
from geopy.distance import geodesic
import re
import io
import time
import requests
import h3
warnings.simplefilter(action='ignore', category=FutureWarning)

def lat_lng_to_h3(lat, lng, resolution=9):    # dir(h3)
    return h3.geo_to_h3(lat, lng, resolution) # geo_to_h3 or latlng_to_cell

def get_poi_distance(lat, lng, poi_type):
    overpass_url = "https://overpass-api.de/api/interpreter"
    radius = 10_000
    if poi_type == "subway":
        overpass_query = f"""
        [out:json];
        node["station"="subway"](around:{radius},{lat},{lng});
        out body;
        """
    else:
        overpass_query = f"""
        [out:json];
        node["amenity"="{poi_type}"](around:{radius},{lat},{lng});
        out body;
        """
    max_retries = 5
    retry_delay = 5  # Задержка между попытками в секундах
    
    for attempt in range(max_retries):
        try:
            response = requests.get(overpass_url, params={'data': overpass_query})
            response.raise_for_status()  # Проверяем HTTP-статус ответа
            data = response.json()       # Пытаемся декодировать JSON
            break
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                print("Max retries reached. Returning default value.")
                return -1  # Возвращаем значение по умолчанию при неудаче
    min_distance = float('inf')
    if len(data['elements']) > 0:
        for element in data['elements']:
            if 'lat' in element and 'lon' in element:
                poi_lat = element['lat']
                poi_lon = element['lon']
            elif 'center' in element:
                poi_lat = element['center']['lat']
                poi_lon = element['center']['lon']
            else:
                continue
            distance = geodesic((lat, lng), (poi_lat, poi_lon)).kilometers
            min_distance = min(min_distance, distance)
    else: # Если объектов не найдено, возвращаем -1 или другое значение по умолчанию
        return -1
    return round(min_distance, 6)

def drop_high_perc_val_columns(df):
    high_perc_val_string = []
    for column in df.columns.to_list():
        perc = round(df[column].isnull().sum()/len(df[column])*100, 1)
        if perc > 20:
            high_perc_val_string.append(str(column))
    print('Новые признаки с большим кол-вом пропусков: ',high_perc_val_string)
    return df

def extract_floors_info(df):
    pattern = r'(\d+)/(\d+)\s*эт'
    def extract_and_fill(row):
        if pd.notna(row['floor']) and pd.notna(row['floors_count']):
            return row['floor'], row['floors_count']
        match = re.search(pattern, row['title'])
        if match:
            extracted_floor = int(match.group(1))
            extracted_floors_count = int(match.group(2))
            floor = row['floor'] if pd.notna(row['floor']) else extracted_floor
            floors_count = row['floors_count'] if pd.notna(row['floors_count']) else extracted_floors_count
            return floor, floors_count
        return row['floor'], row['floors_count']
    df['floor'], df['floors_count'] = zip(*df.apply(extract_and_fill, axis=1))
    
    return df

def determine_city(row):
    point = (row['lat'], row['lng'])
    distances = {city: geodesic(point, coords).kilometers for city, coords in city_coords.items()}
    nearest_city = min(distances, key=distances.get)
    return nearest_city

def clean_area_regex(value):
    value = re.sub(r'[^\d.,]', '', str(value))
    value = value.replace(',', '.')
    if value == '':
        return None
    else:
        return float(value)
    
def fill_missing_by_lat_lng_and_address(df, col='year_buld',
                                        group_cols=['lat', 'lng'],
                                        address_col='address'
                                       ):
    mean_vals = df.groupby(group_cols)[col].mean().round()            # 1) Считаем среднее по заданным колонкам group_cols и округляем
    df['_temp_fill'] = df.set_index(group_cols).index.map(mean_vals)  # 2) Промежуточная колонка для хранения среднего
    df[col] = df[col].fillna(df['_temp_fill'])                        # 3) Заполняем пропуски значениями из _temp_fill
    df.drop(columns=['_temp_fill'], inplace=True)                     # 4) Удаляем временную колонку
    # 5) Заполняем оставшиеся пропуски по моде в рамках одного адреса (если вдруг для данного адреса есть хотя бы одно ненулевое значение)
    for addr in df[df[col].isnull()][address_col].unique():
        addr_vals = df.loc[df[address_col] == addr, col].value_counts()
        if not addr_vals.empty:
            most_common_val = addr_vals.idxmax()  # самое частое значение
            df.loc[(df[address_col] == addr) & (df[col].isnull()), col] = most_common_val
    return df

def fill_missing_rooms(df):
    mean_area = df.groupby('rooms_count')['area'].mean()
    df_filled = df.copy()
    missing_indices = df_filled['rooms_count'].isnull()
    for index in df_filled[missing_indices].index:
        area = df_filled.loc[index, 'area']
        closest_rooms = mean_area.index[np.argmin(np.abs(mean_area.values - area))]
        df_filled.loc[index, 'rooms_count'] = closest_rooms
    return df_filled


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import ks_2samp, ttest_ind


DB_NAME = "rev_data"
DB_USER = "analyst"
DB_PASSWORD = "iPJenuTt"
DB_HOST = "31.184.253.116"
DB_PORT = "5432"
with psycopg2.connect("host='{}' port={} dbname='{}' user={} password={}".format(  DB_HOST
                                                                                 , DB_PORT
                                                                                 , DB_NAME
                                                                                 , DB_USER
                                                                                 , DB_PASSWORD)) as conn:
    sql = """  select address, area, area_kitchen, area_live,
               price_object, renovation, rooms_count,
               type_flat, status_flat, lat, lng,
               year_buld, floors_count, floor, source_id,
               parsed_at, url_link, title
               from flats_active
               where parsed_at >= (select max(date(parsed_at)) from flats_active)
               and lower(title) NOT LIKE '%доля%'
               and lower(description) NOT LIKE '%номер извещения%'
               and lower(description) NOT LIKE '%аукцион%';"""
    
    df = pd.read_sql_query(sql, conn)
# =======================================================================================
# Проверяем количество дубликатов
df['source_id'] = df['source_id'].astype(int)
duplicated_ids = df[df['source_id'].duplicated()]
print(f"Количество дубликатов: {len(duplicated_ids)}")
# Удаляем дубликаты, оставляя первое вхождение
df = df.sort_values(by=['parsed_at', 'year_buld', 'price_object'], ascending=[False, True, True]).drop_duplicates(subset='source_id', keep='first')
print('После смерти дубликатов', df.shape)
# Координаты центров городов
city_coords = {
    "Казань": (55.796127, 49.106414),
    "Самара": (53.195878, 50.100202),
    "Нижний Новгород": (56.326797, 44.006516)
}
df['city'] = df.apply(determine_city, axis=1)
df = df[(df['city'] == 'Нижний Новгород') | (df['city'] == 'Казань') | (df['city'] == 'Самара')]
# city_mapping = {
#     'Самара': 1,
#     'Нижний Новгород': 2,
#     'Казань': 3
# }
# df['city'] = df['city'].map(city_mapping)
# =======================================================================================
df.replace('nan', '', inplace=True)
df.replace('', np.nan, inplace=True)
df = df.dropna(subset=['price_object', 'rooms_count', 'type_flat', 'lat', 'lat', 'url_link'])
df.replace('', np.nan, inplace=True)
df['price_object'] = df['price_object'].astype(int)
df = df[df['price_object']<1_000_000_000]


# №№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№
# Копия данных перед заполнением пропусков
data_before = df.copy()
# №№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№№


# = year_buld ===========================================================================
df = fill_missing_by_lat_lng_and_address(df, col='year_buld')
df = df[(df['year_buld']> 1800) & (df['year_buld']<=2025)]

# = rooms_count =========================================================================
df = fill_missing_rooms(df)
df = df[df['rooms_count']<=7]
# print('После смерти выбрасов в rooms_count', df.shape)
# =======================================================================================
df = df[df['status_flat'] != 2]
df = df.drop(['status_flat'], axis=1)
# print('Оставили только квартиры (без апартов)', df.shape)
df = df[df['type_flat'] != 2]
df = df.drop(['type_flat'], axis=1)
# print('Оставили только вторички (без новостроек)', df.shape)
df = drop_high_perc_val_columns(df)
# ------------------------------------------------------------------------------------------------------------------------------------------------------
# = address =============================================================================
df.loc[df['address'] == 'Казань', 'address'] = np.nan
df.loc[df['address'] == 'Нижний Новгород', 'address'] = np.nan
df.loc[df['address'] == 'Самара', 'address'] = np.nan
df = df[~df['address'].isnull()]
# print('После смерти пустых адресов', df.shape)

# = renovation ==========================================================================
mapping = {
    'Без ремонта': 0,
    'Косметический': 1,
    'Евроремонт': 2,
    'Дизайнерский': 3
}
df['renovation'] = df['renovation'].map(mapping)

# = area_kitchen, area_live, area =======================================================
df['area'] = df['area'].apply(clean_area_regex)
df['area_kitchen'] = df['area_kitchen'].apply(clean_area_regex)
df['area_live'] = df['area_live'].apply(clean_area_regex)
df = df[df['area']<500]
df = df[df['area']>10]
# print('После смерти выбрасов в area', df.shape)
# Заполняем пропуски в area_kitchen
df['area_kitchen'] = df['area_kitchen'].fillna(df['area'] - df['area_live'])
# Заполняем пропуски в area_live
df['area_live'] = df['area_live'].fillna(df['area'] - df['area_kitchen'])
# оставшиеся пропуски заменим значением, проппорциональным среднему по заполненным в отношении в общей площади
# отношения площади гостиной и кухни к общей площади
df['area_live_ratio'] = df['area_live'] / df['area']
df['area_kitchen_ratio'] = df['area_kitchen'] / df['area']

df['area_live'] = df['area_live'].fillna(df['area'] * df['area_live_ratio'].median())
df['area_kitchen'] = df['area_kitchen'].fillna(df['area'] * df['area_kitchen_ratio'].median())

df['area_live_ratio'] = df['area_live'] / df['area']
df['area_kitchen_ratio'] = df['area_kitchen'] / df['area']

# df['combined_ratio'] = df['area_live_ratio'] * df['area_kitchen_ratio']
# Высокое значение combined_ratio может указывать на квартиру с большим жилым пространством и удобной кухней
# Низкое значение может говорить о том, что квартира имеет много "нежилых" зон (например, коридоры, кладовки)
df['area_per_renovation'] = df['area'] * (df['renovation'] + 1)

# = floors_count ========================================================================
df = extract_floors_info(df)
# df = df[(df['floors_count']<80) & (df['floors_count']>0)]
# print('После смерти выбрасов в floors_count', df.shape)

# = distance_to_center ==================================================================
df.loc[df['city'] == 'Нижний Новгород', 'center_lat'] = 56.326797
df.loc[df['city'] == 'Нижний Новгород', 'center_lng'] = 44.006516
df.loc[df['city'] == 'Казань', 'center_lat'] = 55.796127
df.loc[df['city'] == 'Казань', 'center_lng'] = 49.106414
df.loc[df['city'] == 'Самара', 'center_lat'] = 53.195878
df.loc[df['city'] == 'Самара', 'center_lng'] = 50.100202
df['distance_to_center'] = df.apply(
    lambda row: geodesic((row['lat'], row['lng']), (row['center_lat'], row['center_lng'])).kilometers,
    axis=1
)
df = df.loc[df['distance_to_center'] <= 100]

# = h3_categorical ======================================================================
df['h3_categorical'] = df.apply(lambda row: lat_lng_to_h3(row['lat'], row['lng']), axis=1).astype('category').cat.codes

# = distance_to_subway ==================================================================
subway_dist_df = pd.read_csv('subway_dist_df_250508.csv')
df['id'] = df['source_id']
df.set_index('id', inplace=True)
subway_dist_df.set_index('id', inplace=True)
df = df.join(subway_dist_df['distance_to_subway'], how='left')
# для новых данных, в которых значение не заполнено
start_time = time.time()
print(start_time)
df['distance_to_subway'] = df.apply(
    lambda x: get_poi_distance(x['lat'], x['lng'], 'subway') 
              if pd.isna(x['distance_to_subway']) else x['distance_to_subway'], 
    axis=1
)
print('Время расчета: ', round((time.time() - start_time)/60/60, 2), ' ч')
# ------------------------------------------------------------------------------------------------------------------------------------------------------
df = df.drop(['address', 'renovation', 'lat', 'lng', 'floor', 'title', 'center_lat', 'center_lng'], axis=1)
print('ready')

df_df_df = df[['source_id','distance_to_subway']]
df_df_df['id'] = df_df_df['source_id']
df_df_df.to_csv('subway_dist_df_250508.csv', index=False)

























# ===========================================================================================================
# ===========================================================================================================
# Итого:
# Определяем желаемый порядок столбцов
desired_order = [
    # tech_features
    'source_id',
    'url_link',
    'city',
    'parsed_at',

    # significant_features
    'price_object',
    'normalized_price',
    'rooms_count',
    'area_kitchen',
    'area_live',
    'floors_count',
    'distance_to_center',
    'area_live_ratio',
    'area_kitchen_ratio',

    # non_significant_features
    'area',
    'balcony_cat',
    'has_any_lift',
    'height_m',
    'house_type',
    'renovation',
    'window_type',
    'year_buld',
    'floor',
    'sanuzel_multiple',
    'sanuzel_per_room',
    'description_length'
]
df = df[desired_order]
# ===========================================================================================================
try:
    conn = psycopg2.connect("host='{}' port={} dbname='{}' user={} password={}".format(  DB_HOST
                                                                                 , DB_PORT
                                                                                 , DB_NAME
                                                                                 , DB_USER
                                                                                 , DB_PASSWORD))
    cur = conn.cursor()
    create_table_query = """
    DROP TABLE IF EXISTS preprocessed_data;
    
    CREATE TABLE IF NOT EXISTS preprocessed_data (
      source_id           TEXT,
      url_link            TEXT,
      city                TEXT,
      parsed_at           DATE,

      price_object        NUMERIC(20,10),
      normalized_price    NUMERIC(16,8),
      rooms_count         INT,
      area_kitchen        DECIMAL(8, 4),
      area_live           DECIMAL(8, 4),
      floors_count        DECIMAL(8, 4),
      distance_to_center  DECIMAL(8, 4),
      area_live_ratio     DECIMAL(8, 4),
      area_kitchen_ratio  DECIMAL(8, 4),

      area                DECIMAL(8, 4),
      balcony_cat         DECIMAL(8, 4),
      has_any_lift        DECIMAL(8, 4),
      height_m            DECIMAL(8, 4),
      house_type          INT,
      renovation          INT,
      window_type         DECIMAL(8, 4),
      year_buld           DECIMAL(8, 4),
      floor               DECIMAL(8, 4),
      sanuzel_multiple    INT,
      sanuzel_per_room    DECIMAL(8, 4),
      description_length  INT

    );
    """
    cur.execute(create_table_query)
    conn.commit()

    # TRUNCATE (очищаем таблицу перед новой записью):
    truncate_table_query = "TRUNCATE TABLE preprocessed_data;"
    cur.execute(truncate_table_query)
    conn.commit()

    # Загрузка DataFrame в PostgreSQL
    # Сначала сохраняем содержимое df в буфер StringIO в формате CSV (без заголовков, без индекса).
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False, sep='\t')
    buffer.seek(0) # «Перематываем» указатель в начало буфера

    #  Загружаем данные из буфера в таблицу
    cur.copy_from(buffer, 'preprocessed_data', sep='\t')

    # Фиксируем изменения
    conn.commit()

except Exception as e:
    print("Ошибка при работе с PostgreSQL:", e)

finally:
    if conn:
        cur.close()
        conn.close()
print('Готово')
