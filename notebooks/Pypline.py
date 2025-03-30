import numpy as np
import pandas as pd
import psycopg2
import warnings
from geopy.distance import geodesic
import re
import io
import time
warnings.simplefilter(action='ignore', category=FutureWarning)
# =====================================================================================
def drop_high_perc_val_columns(df):
    high_perc_val_string = []
    for column in df.columns.to_list():
        perc = round(df[column].isnull().sum()/len(df[column])*100, 1)
        if perc > 40:
#             df = df.drop(column, axis=1)
#             print(column, perc)
            high_perc_val_string.append(str(column))
    # print('Новые признаки с большим кол-вом пропусков: ',high_perc_val_string)
    
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

# Функция для определения ближайшего города
def determine_city(row):
    # Координаты текущей точки
    point = (row['lat'], row['lng'])
    # Вычисление расстояний до всех городов
    distances = {city: geodesic(point, coords).kilometers for city, coords in city_coords.items()}
    # Выбор города с минимальным расстоянием
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

    # 1) Считаем среднее по заданным колонкам group_cols и округляем
    mean_vals = df.groupby(group_cols)[col].mean().round()

    # 2) Промежуточная колонка для хранения среднего
    df['_temp_fill'] = df.set_index(group_cols).index.map(mean_vals)
    # 3) Заполняем пропуски значениями из _temp_fill
    df[col] = df[col].fillna(df['_temp_fill'])
    # 4) Удаляем временную колонку
    df.drop(columns=['_temp_fill'], inplace=True)

    # 5) Заполняем оставшиеся пропуски по моде в рамках одного адреса
    #    (если вдруг для данного адреса есть хотя бы одно ненулевое значение)
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

# =====================================================================================
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
    sql = "select * from flats;"
    df = pd.read_sql_query(sql, conn)
# ====================================================================================
df.replace('nan', '', inplace=True)
df.replace('', np.nan, inplace=True)
df = df[['address', 'area', 'area_kitchen', 'area_live', 'balcony_cat', 'normalized_price',
       'has_any_lift', 'deadline_end_bd', 'height_m', 'house_type',
       'price_object', 'renovation', 'rooms_count', 'sanuzel_combined',
       'sanuzel_separate', 'type_flat', 'status_flat', 'lat', 'lng',
       'window_type', 'year_buld', 'floors_count', 'floor', 'source_id',
       'city', 'parsed_at', 'url_link', 'description', 'title']]
# print('Начало', df.shape)
df = df.dropna(subset=['price_object', 'rooms_count', 'type_flat', 'lat', 'lat', 'url_link'])
df.replace('', np.nan, inplace=True)
df = df[df['price_object']<1_000_000_000]
df['normalized_price'] = df['normalized_price'].fillna(round(df['price_object'] / df['area'], 2))
# = rooms_count =====================================================
df = fill_missing_rooms(df)
df = df[df['rooms_count']<7]
# print('После смерти выбрасов в rooms_count', df.shape)
# ======================================================
# Проверяем количество дубликатов
duplicated_ids = df[df['source_id'].duplicated()]
# print(f"Количество дубликатов: {len(duplicated_ids)}")
# Удаляем дубликаты, оставляя первое вхождение
df = df.sort_values(by=['parsed_at', 'price_object'], ascending=[False, True]).drop_duplicates(subset='source_id', keep='first')
# print('После смерти дубликатов', df.shape)
# Координаты центров городов
city_coords = {
    "Казань": (55.796127, 49.106414),
    "Самара": (53.195878, 50.100202),
    "Нижний Новгород": (56.326797, 44.006516)
}
df['city'] = df.apply(determine_city, axis=1)
# =====================================================================================
df = drop_high_perc_val_columns(df)
df = df[(df['city'] == 'Нижний Новгород') | (df['city'] == 'Казань') | (df['city'] == 'Самара')]
df = df[df['status_flat'] != 2]
df = df.drop(['status_flat'], axis=1)
# print('Оставили только квартиры (без апартов)', df.shape)
# ===========================================================================================================================
# = address =====================================================
df.loc[df['address'] == 'Казань', 'address'] = np.nan
df.loc[df['address'] == 'Нижний Новгород', 'address'] = np.nan
df.loc[df['address'] == 'Самара', 'address'] = np.nan
df = df[~df['address'].isnull()]
# print('После смерти пустых адресов', df.shape)

# = area_kitchen, area_live, area =====================================================
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

df = df.drop(['deadline_end_bd'], axis=1)
df = fill_missing_by_lat_lng_and_address(df, col='year_buld')

mode_value = df['year_buld'].mode()[0]
df['year_buld'] = df['year_buld'].fillna(mode_value)
df = df[df['year_buld']>1800]
# print('После смерти выбрасов в year_buld', df.shape)

# ====================================================================================================
# = floors_count,floor =====================================================
df = extract_floors_info(df)
df['floor_ratio'] = df['floor']/df['floors_count']
df['floor_to_live_ratio'] = df['floor_ratio'] / df['area_live_ratio'].replace(0, 1e-10)
df = df[(df['floors_count']<80) & (df['floors_count']>0)]
# print('После смерти выбрасов в floors_count', df.shape)
# ====================================================================================================

# = has_any_lift =====================================================
df = fill_missing_by_lat_lng_and_address(df, col='has_any_lift')
df.loc[(df['has_any_lift'].isna()) & (df['floors_count'] > 5), 'has_any_lift'] = 1
df.loc[(df['has_any_lift'].isna()) & (df['floors_count'] <= 5), 'has_any_lift'] = 0

# # = renovation =====================================================
# # 0 - Без ремонта, 1 - косметический, 2 - евро, 3 - дизайнерский
df['renovation'] = df['renovation'].replace('Без ремонта', 0).replace('Косметический', 1).replace('Евроремонт', 2).replace('Дизайнерский', 3).replace('Требуется', 4)
df.loc[df['renovation'].isna(), 'renovation'] = 4
df['renovation'] = df['renovation'].astype(int)

# = sanuzel_combined, sanuzel_separate =====================================================
# Инициализируем колонку
# df['sanuzel_multiple'] = 0
# Условие 0: если его нет (ну мало ли)
df.loc[(df['sanuzel_combined'] == 0) & (df['sanuzel_separate'] == 0), 'sanuzel_multiple'] = 0
# Условие 1: только раздельный
df.loc[(df['sanuzel_combined'] == 0) & (df['sanuzel_separate'] == 1), 'sanuzel_multiple'] = 1
# Условие 2: только совмещённый
df.loc[(df['sanuzel_combined'] == 1) & (df['sanuzel_separate'] == 0), 'sanuzel_multiple'] = 1
# Условие 3: и совмещённый, и раздельный
df.loc[(df['sanuzel_combined'] == 1) & (df['sanuzel_separate'] == 1), 'sanuzel_multiple'] = 2
df = df.drop(['sanuzel_combined', 'sanuzel_separate'], axis=1)
df['sanuzel_per_room'] = df['rooms_count']/ df['sanuzel_multiple']
df['sanuzel_multiple'] = df['sanuzel_multiple'].astype(int)

# = height_m =====================================================
def scale_to_10(x):
    while x > 10:
        x /= 10
    return x
df['height_m'] = df['height_m'].apply(scale_to_10)
df = fill_missing_by_lat_lng_and_address(df, col='height_m')
mode_value = df['height_m'].mode()[0]
df['height_m'] = df['height_m'].fillna(mode_value)

# = balcony_cat =====================================================
mode_value = df['balcony_cat'].mode()[0]
df['balcony_cat'] = df['balcony_cat'].fillna(mode_value)

# = window_type =====================================================
df = fill_missing_by_lat_lng_and_address(df, col='window_type')
mode_value = df['window_type'].mode()[0]
df['window_type'] = df['window_type'].fillna(mode_value)

# = house_type =====================================================
mode_value = df['house_type'].mode()[0]
df['house_type'] = df['house_type'].fillna(mode_value)
df['house_type'] = df['house_type'].astype('category')
df['house_type'] = df['house_type'].cat.codes

# ===========================================================================================================================
df = df.drop('address', axis=1)
df['price_object'] = df['price_object'].astype(int)
# print('000', df.shape)

# = distance_to_center =====================================================
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
df = df.drop(['center_lat', 'center_lng', 'lat', 'lng', 'title'], axis=1)

# = description_length =====================================================
# Количество слов в описании
df['description_length'] = df['description'].apply(lambda x: len(str(x).split()) if pd.notnull(x) else 0)
df = df.drop(['description'], axis=1)


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
    'type_flat',
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
      type_flat           INT,
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
