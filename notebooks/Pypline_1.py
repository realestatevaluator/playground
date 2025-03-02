import numpy as np
import pandas as pd
import psycopg2
import warnings
import re
warnings.simplefilter(action='ignore', category=FutureWarning)
# =====================================================================================
def remove_outliers_iqr(df, column):
    Q1 = df[column].quantile(0.25)
    Q3 = df[column].quantile(0.75)
    IQR = Q3 - Q1
    lower_bound = Q1 - 1.5 * IQR
    upper_bound = Q3 + 1.5 * IQR
    df_filtered = df[(df[column] >= lower_bound) & (df[column] <= upper_bound)]
    return df_filtered

def drop_high_perc_val_columns(df):
    high_perc_val_string = []
    for column in df.columns.to_list():
        perc = round(df[column].isnull().sum()/len(df[column])*100, 1)
        if perc > 55:
            df = df.drop(column, axis=1)
            high_perc_val_string.append(str(column))
    print('Новые признаки с большим кол-вом пропусков: ',high_perc_val_string)
    
    return df

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
# =====================================================================================
df.replace('', np.nan, inplace=True)
df = df[['address', 'area', 'area_kitchen', 'area_live', 'balcony_cat',
       'has_any_lift', 'deadline_end_bd', 'height_m', 'house_type',
       'price_object', 'renovation', 'rooms_count', 'sanuzel_combined',
       'sanuzel_separate', 'type_flat', 'status_flat', 'lat', 'lng',
       'window_type', 'year_buld', 'floors_count', 'floor', 'source_id',
       'city']]
df = df.dropna(subset=['price_object','rooms_count', 'type_flat', 'lat', 'lat'])
# sanuzel

# # 2. Удаляем технические признаки
# features_technical = [   'id_flat_adj',
#                          'title',
#                          'url_link',
#                          'id',
#                          'parsed_at',
#                          'updated_at',
#                          'load_dt',
#                         'name_bd_house',
#                         'description',
#                         'finishing_type',
#                         'data_source',
#                         'pass_lift_count',
#                         'cargo_lift_count',
#                         'has_passenger_lift',
#                         'has_cargo_lift',
#                         'normalized_price',
#                         'balcony_cnt',
#                         'loggia_cnt',
#                         'emergency',
#                       'has_concierge',
#                       'has_gas_supply',
#                       'has_garbage_chute',
#                       'has_playground',
#                       'has_sports_ground',
#                       'has_closed_territory',
#                       'has_furniture_kitchen',
#                       'has_furniture_bed',
#                       'has_furniture_wardrobe',
#                       'kindergarten_around', 'school_around', 'hospital_around',
#                       'shops_around', 'sport_around', 'kindergarten_distance',
#                       'school_distance', 'hospital_distance', 'shops_distance', 'sport_distance',
#                       'parking_underground', 'parking_many_levels', 'has_water_heater', 'has_air_cond',
#                       'has_dishwasher', 'has_washing_machine', 'has_fridge']
# for feature in features_technical:
#     if feature in df.columns.to_list():
#         df = df.drop(feature, axis=1)

df = drop_high_perc_val_columns(df)
df = df[(df['city'] == 'Нижний Новгород') | (df['city'] == 'Казань') | (df['city'] == 'Самара')]
df = df[df['status_flat'] != 2]
df = df.drop(['status_flat'], axis=1)

# ===========================================================================================================================
# = address =====================================================
df = df[~df['address'].isnull()]
df.loc[df['address'] == 'Казань', 'address'] = np.nan
df.loc[df['address'] == 'Нижний Новгород', 'address'] = np.nan
df.loc[df['address'] == 'Самара', 'address'] = np.nan

# = area_kitchen, area_live, area =====================================================
df['area_kitchen'] = df['area_kitchen'].apply(clean_area_regex)
df['area'] = df['area'].apply(clean_area_regex)
df['area_live'] = df['area_live'].apply(clean_area_regex)
# Заполняем пропуски в area_kitchen
df['area_kitchen'] = df['area_kitchen'].fillna(df['area'] - df['area_live'])
# Заполняем пропуски в area_live
df['area_live'] = df['area_live'].fillna(df['area'] - df['area_kitchen'])

# оставшиеся пропуски заменим значением, проппорциональным среднему по заполненным в отношении в общей площади
# отношения площади гостиной и кухни к общей площади
df['area_live_ratio'] = df['area_live'] / df['area']
df['area_kitchen_ratio'] = df['area_kitchen'] / df['area']

df['area_live'] = df['area_live'].fillna(df['area'] * df['area_live_ratio'].mean())
df['area_kitchen'] = df['area_kitchen'].fillna(df['area'] * df['area_kitchen_ratio'].mean())

df = df.drop(['area_live_ratio', 'area_kitchen_ratio'], axis=1)

# = rooms_count =====================================================
df = fill_missing_rooms(df)

# = has_any_lift =====================================================
df = fill_missing_by_lat_lng_and_address(df, col='has_any_lift')
df.loc[(df['has_any_lift'].isna()) & (df['floors_count'] > 5), 'has_any_lift'] = 1
df.loc[(df['has_any_lift'].isna()) & (df['floors_count'] <= 5), 'has_any_lift'] = 0

# = year_buld, deadline_end_bd =====================================================
# Удаляем все не-цифровые символы (буквы, пробелы, знаки препинания):
df['deadline_end_bd'] = df['deadline_end_bd'].str.replace(r'[^0-9]+', '', regex=True)
df['deadline_end_bd'] = df['deadline_end_bd'].str[-4:]
df[['deadline_end_bd', 'year_buld']] = df[['deadline_end_bd', 'year_buld']].astype(float)
df['year_buld'] = df['year_buld'].where(df['year_buld'] >= 1800, np.nan)
df['year_buld'] = df['year_buld'].fillna(df['deadline_end_bd'])
df = fill_missing_by_lat_lng_and_address(df, col='year_buld')
df = df.drop(['deadline_end_bd'], axis=1)
mode_value = df['year_buld'].mode()[0]
df['year_buld'] = df['year_buld'].fillna(mode_value)
# = renovation =====================================================
# 0 - Без ремонта, 1 - косметический, 2 - евро, 3 - дизайнерский, 4 - требуется
df['renovation'] = df['renovation'].replace('Без ремонта', 0).replace('Косметический', 1).replace('Евроремонт', 2).replace('Дизайнерский', 3).replace('Требуется', 4)
df = fill_missing_by_lat_lng_and_address(df, col='renovation')

# = sanuzel_combined, sanuzel_separate =====================================================
# Инициализируем колонку
df['sanuzel_multiple'] = 0
# Условие 0: если его нет (ну мало ли)
df.loc[(df['sanuzel_combined'] == 0) & (df['sanuzel_separate'] == 0), 'sanuzel_multiple'] = 0
# Условие 1: только совмещённый
df.loc[(df['sanuzel_combined'] == 1) & (df['sanuzel_separate'] == 0), 'sanuzel_multiple'] = 1
# Условие 2: только раздельный
df.loc[(df['sanuzel_combined'] == 0) & (df['sanuzel_separate'] == 1), 'sanuzel_multiple'] = 2
# Условие 3: и совмещённый, и раздельный
df.loc[(df['sanuzel_combined'] == 1) & (df['sanuzel_separate'] == 1), 'sanuzel_multiple'] = 3

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

# = floors_count,floor =====================================================
df = fill_missing_by_lat_lng_and_address(df, col='floors_count') 


# = house_type =====================================================
mode_value = df['house_type'].mode()[0]
df['house_type'] = df['house_type'].fillna(mode_value)
df['house_type'] = df['house_type'].astype('category')
df['house_type'] = df['house_type'].cat.codes

# ===========================================================================================================================
df = df.drop('address', axis=1)
df['price_object'] = df['price_object'].astype(int)
df = remove_outliers_iqr(df, 'price_object')
df = remove_outliers_iqr(df, 'area')
df = df.dropna(subset=['floors_count','floor']) #

try:
    conn = psycopg2.connect("host='{}' port={} dbname='{}' user={} password={}".format(  DB_HOST
                                                                                 , DB_PORT
                                                                                 , DB_NAME
                                                                                 , DB_USER
                                                                                 , DB_PASSWORD))
    cur = conn.cursor()
    create_table_query = """
    CREATE TABLE IF NOT EXISTS preprocessed_data (
      area              DECIMAL(8, 4),
      area_kitchen      DECIMAL(8, 4),
      area_live         DECIMAL(8, 4),
      balcony_cat       DECIMAL(8, 4),
      has_any_lift      DECIMAL(8, 4),
      height_m          DECIMAL(8, 4),
      house_type        INT,
      price_object      NUMERIC(12,2),
      renovation        INT,
      rooms_count       INT,
      sanuzel_combined  INT,
      sanuzel_separate  INT,
      type_flat         INT,
      lat               NUMERIC(8, 6),
      lng               NUMERIC(8, 6),
      window_type       DECIMAL(8, 4),
      year_buld         DECIMAL(8, 4),
      floors_count      DECIMAL(8, 4),
      floor             DECIMAL(8, 4),
      source_id         TEXT,
      city              TEXT,
      sanuzel_multiple  INT
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