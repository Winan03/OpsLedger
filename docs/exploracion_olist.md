# Exploracion inicial del dataset Olist

Generado: 2026-10-06T20:36:29

## Metricas de duplicados

- **Filas sobrantes (`keep='first'`)**: Numero de filas redundantes que se eliminarian al desduplicar (se conserva la 1ra aparicion y se cuentan las sobrantes).
- **Filas involucradas (`keep=False`)**: Numero total de filas que forman parte de algun grupo de duplicados (incluye la 1ra aparicion y todas sus repeticiones).

## Clasificacion de valores nulos destacados

### 1. Nulos esperables (opcionales por dinamica de negocio)
- **`olist_order_reviews_dataset.csv`**: `review_comment_title` (87,656 nulos, 88.34%) y `review_comment_message` (58,247 nulos, 58.70%). Son **nulos esperables**: el cliente otorga una calificacion de 1 a 5 estrellas sin estar obligado a escribir un titulo o comentario en texto libre.

### 2. Nulos por error de catalogo / datos faltantes
- **`olist_products_dataset.csv`**: `product_category_name`, `product_name_lenght`, `product_description_lenght`, `product_photos_qty` (610 nulos, 1.85%). Son **errores / datos faltantes de catalogo**: fichas de producto incompletas registradas sin categoria ni metadata basica.
- **`olist_products_dataset.csv`**: `product_weight_g`, `product_length_cm`, `product_height_cm`, `product_width_cm` (2 nulos, 0.01%). Son **errores / datos faltantes de catalogo**: atributos fisicos logisticos indispensables que omitieron su peso/dimensiones.

## Archivos procesados

| Archivo | Filas | Columnas |
| --- | --- | --- |
| olist_customers_dataset.csv | 99441 | 5 |
| olist_geolocation_dataset.csv | 1000163 | 5 |
| olist_order_items_dataset.csv | 112650 | 7 |
| olist_order_payments_dataset.csv | 103886 | 5 |
| olist_order_reviews_dataset.csv | 99224 | 7 |
| olist_orders_dataset.csv | 99441 | 8 |
| olist_products_dataset.csv | 32951 | 9 |
| olist_sellers_dataset.csv | 3095 | 4 |
| product_category_name_translation.csv | 71 | 2 |

## Problemas encontrados

- `olist_geolocation_dataset.csv` tiene 261831 filas duplicadas completas sobrantes y 390005 filas involucradas.
- `olist_order_reviews_dataset.csv` tiene 814 filas sobrantes y 1603 filas involucradas con id principal duplicado (review_id).
- `products.product_category_name -> translation.product_category_name` presenta 13 filas huerfanas (2 valores distintos). Ejemplos: pc_gamer, portateis_cozinha_e_preparadores_de_alimentos.
- `customers.customer_zip_code_prefix -> geolocation.geolocation_zip_code_prefix` presenta 278 filas huerfanas (157 valores distintos). Ejemplos: 72300, 11547, 64605, 72465, 7729, 72904, 35408, 78554, 73369, 8980.
- `sellers.seller_zip_code_prefix -> geolocation.geolocation_zip_code_prefix` presenta 7 filas huerfanas (7 valores distintos). Ejemplos: 82040, 91901, 72580, 2285, 7412, 71551, 37708.
- `orders`: regla `delivered_sin_fecha_entrega_cliente` afecta 8 filas (0.01%). Ejemplos: 2d1e2d5bf4dc7227b3bfebb81328c15f, f5dd62b788049ad9fc0526e3ad11a097, 2ebdfc4f15f23b91474edf87475f108e, e69f75a717d64fc5ecdfae42b2e8e086, 0d3268bad9b086af767785e3f0fc0133, 2d858f451373b04fb5c984a1cc2defaf, ab7c89dc1bf4a1ead9d6ec1ec8968a84, 20edc82cf5400ce95e1afacc25798b31.
- `orders`: regla `transportista_antes_de_aprobacion` afecta 1359 filas (1.37%). Ejemplos: dcb36b511fcac050b97cd5c05de84dc3, 688052146432ef8253587b930b01a06d, 58d4c4747ee059eeeb865b349b41f53a, 412fccb2b44a99b36714bca3fef8ad7b, 56a4ac10a4a8f2ba7693523bb439eede, 32e4fa9bb468884309b58b9348de70c3, 4df92d82d79c3b52c7138679fa9b07fc, 16e38caa92e342c7780f68832f832d4d, b9afddbdcfadc9a87b41a83271c3e888, 6051e6d3da9a50b7325cbe9c81025062.
- `orders`: regla `entrega_cliente_antes_de_transportista` afecta 23 filas (0.02%). Ejemplos: a1abeb653a4d4cd1e142ccb8c82cd069, 383aa8b2724fe452d9ccd9934a8c628b, cb1134f9010d242e9515ad1c78ec0c39, dceb62e8fa94b46006c9554fed743df0, 5f9d46795c3126674e52becb3a1a517f, 8c78d01de3a9009e23d6877a7cc9be20, b27af682321527a6349f1761eb3f360c, 1cc3ae63caffff2d6c3ee3e78e074acf, e37f11cae9985ca58f0b56f268720537, fa3e37584f4fdb1ded0e0de700dfcb4e.
- `orders`: regla `no_delivered_con_fecha_entrega_cliente` afecta 6 filas (0.01%). Ejemplos: 1950d777989f6a877539f53795b4c3c3, dabf2b0e35b423f94618bf965fcb7514, 770d331c84e5b214bd9dc70a10b829d0, 8beb59392e21af5eb9547ae1a9938d06, 65d1e226dfaeb8cdc42f665422522d14, 2c45c33d2f9cb8ff8b1c86cc28c11c30.
- `orders`: regla `delivered_sin_fecha_transportista` afecta 2 filas (0.00%). Ejemplos: 2aa91108853cecb43c84a5dc5b277475, 2d858f451373b04fb5c984a1cc2defaf.
- `orders`: regla `delivered_sin_fecha_aprobacion` afecta 14 filas (0.01%). Ejemplos: e04abd8149ef81b95221e88f6ed9ab6a, 8a9adc69528e1001fc68dd0aaebbb54a, 7013bcfc1c97fe719a7b5e05e61c12db, 5cf925b116421afa85ee25e99b4c34fb, 12a95a3c06dbaec84bcfb0e2da5d228a, c1d4211b3dae76144deccd6c74144a88, d69e5d356402adc8cf17e08b5033acfb, d77031d6a3c8a52f019764e68f211c69, 7002a78c79c519ac54022d4f8a65e6e8, 2eecb0d85f281280f79fa00f9cec1a95.

## Relaciones confirmadas

- `orders.customer_id -> customers.customer_id` sin huerfanos detectados.
- `order_items.order_id -> orders.order_id` sin huerfanos detectados.
- `order_payments.order_id -> orders.order_id` sin huerfanos detectados.
- `order_reviews.order_id -> orders.order_id` sin huerfanos detectados.
- `order_items.product_id -> products.product_id` sin huerfanos detectados.
- `order_items.seller_id -> sellers.seller_id` sin huerfanos detectados.

## Columnas de fecha

| Archivo | Columna | Min | Max | Fechas validas | Fechas invalidas |
| --- | --- | --- | --- | --- | --- |
| olist_order_items_dataset.csv | shipping_limit_date | 2016-09-19T00:15:34 | 2020-04-09T22:35:08 | 112650 | 0 |
| olist_order_reviews_dataset.csv | review_creation_date | 2016-10-02T00:00:00 | 2018-08-31T00:00:00 | 99224 | 0 |
| olist_order_reviews_dataset.csv | review_answer_timestamp | 2016-10-07T18:32:28 | 2018-10-29T12:27:35 | 99224 | 0 |
| olist_orders_dataset.csv | order_purchase_timestamp | 2016-09-04T21:15:19 | 2018-10-17T17:30:18 | 99441 | 0 |
| olist_orders_dataset.csv | order_approved_at | 2016-09-15T12:16:38 | 2018-09-03T17:40:06 | 99281 | 0 |
| olist_orders_dataset.csv | order_delivered_carrier_date | 2016-10-08T10:34:01 | 2018-09-11T19:48:28 | 97658 | 0 |
| olist_orders_dataset.csv | order_delivered_customer_date | 2016-10-11T13:46:32 | 2018-10-17T13:22:46 | 96476 | 0 |
| olist_orders_dataset.csv | order_estimated_delivery_date | 2016-09-30T00:00:00 | 2018-11-12T00:00:00 | 99441 | 0 |

## Reglas de validacion candidatas

- Cada tabla con id principal debe rechazar duplicados del id declarado.
- `orders.customer_id` debe existir en `customers.customer_id`.
- `order_items.order_id`, `order_payments.order_id` y `order_reviews.order_id` deben existir en `orders.order_id`.
- `order_items.product_id` debe existir en `products.product_id`.
- `order_items.seller_id` debe existir en `sellers.seller_id`.
- Las categorias no nulas de `products` deben existir en la tabla de traduccion.
- Una entrega al cliente no puede ser anterior a la compra.
- Un pedido `delivered` debe tener fecha de entrega al cliente.
- Las fechas deben seguir el orden compra <= aprobacion <= entrega a transportista <= entrega a cliente cuando existan.
- La fecha estimada de entrega no deberia ser anterior a la compra.

## Detalle por archivo

### olist_customers_dataset.csv

| Metrica | Valor |
| --- | --- |
| Filas | 99441 |
| Columnas | 5 |
| Filas duplicadas completas sobrantes | 0 |
| Filas duplicadas completas involucradas | 0 |
| Id principal evaluado | customer_id |
| Filas sobrantes con id principal duplicado | 0 |
| Filas involucradas con id principal duplicado | 0 |

#### Tipos de datos

| Columna | Tipo pandas |
| --- | --- |
| customer_id | str |
| customer_unique_id | str |
| customer_zip_code_prefix | int64 |
| customer_city | str |
| customer_state | str |

#### Nulos por columna

| Columna | Nulos | % |
| --- | --- | --- |
| customer_id | 0 | 0.00% |
| customer_unique_id | 0 | 0.00% |
| customer_zip_code_prefix | 0 | 0.00% |
| customer_city | 0 | 0.00% |
| customer_state | 0 | 0.00% |

### olist_geolocation_dataset.csv

| Metrica | Valor |
| --- | --- |
| Filas | 1000163 |
| Columnas | 5 |
| Filas duplicadas completas sobrantes | 261831 |
| Filas duplicadas completas involucradas | 390005 |
| Id principal evaluado | No definido |
| Filas sobrantes con id principal duplicado | No aplica |
| Filas involucradas con id principal duplicado | No aplica |

#### Tipos de datos

| Columna | Tipo pandas |
| --- | --- |
| geolocation_zip_code_prefix | int64 |
| geolocation_lat | float64 |
| geolocation_lng | float64 |
| geolocation_city | str |
| geolocation_state | str |

#### Nulos por columna

| Columna | Nulos | % |
| --- | --- | --- |
| geolocation_zip_code_prefix | 0 | 0.00% |
| geolocation_lat | 0 | 0.00% |
| geolocation_lng | 0 | 0.00% |
| geolocation_city | 0 | 0.00% |
| geolocation_state | 0 | 0.00% |

### olist_order_items_dataset.csv

| Metrica | Valor |
| --- | --- |
| Filas | 112650 |
| Columnas | 7 |
| Filas duplicadas completas sobrantes | 0 |
| Filas duplicadas completas involucradas | 0 |
| Id principal evaluado | order_id, order_item_id |
| Filas sobrantes con id principal duplicado | 0 |
| Filas involucradas con id principal duplicado | 0 |

#### Tipos de datos

| Columna | Tipo pandas |
| --- | --- |
| order_id | str |
| order_item_id | int64 |
| product_id | str |
| seller_id | str |
| shipping_limit_date | str |
| price | float64 |
| freight_value | float64 |

#### Nulos por columna

| Columna | Nulos | % |
| --- | --- | --- |
| order_id | 0 | 0.00% |
| order_item_id | 0 | 0.00% |
| product_id | 0 | 0.00% |
| seller_id | 0 | 0.00% |
| shipping_limit_date | 0 | 0.00% |
| price | 0 | 0.00% |
| freight_value | 0 | 0.00% |

#### Rangos de fechas

| Columna | Min | Max | Fechas validas | Fechas invalidas |
| --- | --- | --- | --- | --- |
| shipping_limit_date | 2016-09-19T00:15:34 | 2020-04-09T22:35:08 | 112650 | 0 |

### olist_order_payments_dataset.csv

| Metrica | Valor |
| --- | --- |
| Filas | 103886 |
| Columnas | 5 |
| Filas duplicadas completas sobrantes | 0 |
| Filas duplicadas completas involucradas | 0 |
| Id principal evaluado | order_id, payment_sequential |
| Filas sobrantes con id principal duplicado | 0 |
| Filas involucradas con id principal duplicado | 0 |

#### Tipos de datos

| Columna | Tipo pandas |
| --- | --- |
| order_id | str |
| payment_sequential | int64 |
| payment_type | str |
| payment_installments | int64 |
| payment_value | float64 |

#### Nulos por columna

| Columna | Nulos | % |
| --- | --- | --- |
| order_id | 0 | 0.00% |
| payment_sequential | 0 | 0.00% |
| payment_type | 0 | 0.00% |
| payment_installments | 0 | 0.00% |
| payment_value | 0 | 0.00% |

### olist_order_reviews_dataset.csv

| Metrica | Valor |
| --- | --- |
| Filas | 99224 |
| Columnas | 7 |
| Filas duplicadas completas sobrantes | 0 |
| Filas duplicadas completas involucradas | 0 |
| Id principal evaluado | review_id |
| Filas sobrantes con id principal duplicado | 814 |
| Filas involucradas con id principal duplicado | 1603 |

#### Tipos de datos

| Columna | Tipo pandas |
| --- | --- |
| review_id | str |
| order_id | str |
| review_score | int64 |
| review_comment_title | str |
| review_comment_message | str |
| review_creation_date | str |
| review_answer_timestamp | str |

#### Nulos por columna

| Columna | Nulos | % |
| --- | --- | --- |
| review_id | 0 | 0.00% |
| order_id | 0 | 0.00% |
| review_score | 0 | 0.00% |
| review_comment_title | 87656 | 88.34% |
| review_comment_message | 58247 | 58.70% |
| review_creation_date | 0 | 0.00% |
| review_answer_timestamp | 0 | 0.00% |

#### Rangos de fechas

| Columna | Min | Max | Fechas validas | Fechas invalidas |
| --- | --- | --- | --- | --- |
| review_creation_date | 2016-10-02T00:00:00 | 2018-08-31T00:00:00 | 99224 | 0 |
| review_answer_timestamp | 2016-10-07T18:32:28 | 2018-10-29T12:27:35 | 99224 | 0 |

### olist_orders_dataset.csv

| Metrica | Valor |
| --- | --- |
| Filas | 99441 |
| Columnas | 8 |
| Filas duplicadas completas sobrantes | 0 |
| Filas duplicadas completas involucradas | 0 |
| Id principal evaluado | order_id |
| Filas sobrantes con id principal duplicado | 0 |
| Filas involucradas con id principal duplicado | 0 |

#### Tipos de datos

| Columna | Tipo pandas |
| --- | --- |
| order_id | str |
| customer_id | str |
| order_status | str |
| order_purchase_timestamp | str |
| order_approved_at | str |
| order_delivered_carrier_date | str |
| order_delivered_customer_date | str |
| order_estimated_delivery_date | str |

#### Nulos por columna

| Columna | Nulos | % |
| --- | --- | --- |
| order_id | 0 | 0.00% |
| customer_id | 0 | 0.00% |
| order_status | 0 | 0.00% |
| order_purchase_timestamp | 0 | 0.00% |
| order_approved_at | 160 | 0.16% |
| order_delivered_carrier_date | 1783 | 1.79% |
| order_delivered_customer_date | 2965 | 2.98% |
| order_estimated_delivery_date | 0 | 0.00% |

#### Rangos de fechas

| Columna | Min | Max | Fechas validas | Fechas invalidas |
| --- | --- | --- | --- | --- |
| order_purchase_timestamp | 2016-09-04T21:15:19 | 2018-10-17T17:30:18 | 99441 | 0 |
| order_approved_at | 2016-09-15T12:16:38 | 2018-09-03T17:40:06 | 99281 | 0 |
| order_delivered_carrier_date | 2016-10-08T10:34:01 | 2018-09-11T19:48:28 | 97658 | 0 |
| order_delivered_customer_date | 2016-10-11T13:46:32 | 2018-10-17T13:22:46 | 96476 | 0 |
| order_estimated_delivery_date | 2016-09-30T00:00:00 | 2018-11-12T00:00:00 | 99441 | 0 |

#### Valores frecuentes en estado/categoria

**order_status**

| Valor | Frecuencia |
| --- | --- |
| delivered | 96478 |
| shipped | 1107 |
| canceled | 625 |
| unavailable | 609 |
| invoiced | 314 |
| processing | 301 |
| created | 5 |
| approved | 2 |

### olist_products_dataset.csv

| Metrica | Valor |
| --- | --- |
| Filas | 32951 |
| Columnas | 9 |
| Filas duplicadas completas sobrantes | 0 |
| Filas duplicadas completas involucradas | 0 |
| Id principal evaluado | product_id |
| Filas sobrantes con id principal duplicado | 0 |
| Filas involucradas con id principal duplicado | 0 |

#### Tipos de datos

| Columna | Tipo pandas |
| --- | --- |
| product_id | str |
| product_category_name | str |
| product_name_lenght | float64 |
| product_description_lenght | float64 |
| product_photos_qty | float64 |
| product_weight_g | float64 |
| product_length_cm | float64 |
| product_height_cm | float64 |
| product_width_cm | float64 |

#### Nulos por columna

| Columna | Nulos | % |
| --- | --- | --- |
| product_id | 0 | 0.00% |
| product_category_name | 610 | 1.85% |
| product_name_lenght | 610 | 1.85% |
| product_description_lenght | 610 | 1.85% |
| product_photos_qty | 610 | 1.85% |
| product_weight_g | 2 | 0.01% |
| product_length_cm | 2 | 0.01% |
| product_height_cm | 2 | 0.01% |
| product_width_cm | 2 | 0.01% |

#### Valores frecuentes en estado/categoria

**product_category_name**

| Valor | Frecuencia |
| --- | --- |
| cama_mesa_banho | 3029 |
| esporte_lazer | 2867 |
| moveis_decoracao | 2657 |
| beleza_saude | 2444 |
| utilidades_domesticas | 2335 |
| automotivo | 1900 |
| informatica_acessorios | 1639 |
| brinquedos | 1411 |
| relogios_presentes | 1329 |
| telefonia | 1134 |

### olist_sellers_dataset.csv

| Metrica | Valor |
| --- | --- |
| Filas | 3095 |
| Columnas | 4 |
| Filas duplicadas completas sobrantes | 0 |
| Filas duplicadas completas involucradas | 0 |
| Id principal evaluado | seller_id |
| Filas sobrantes con id principal duplicado | 0 |
| Filas involucradas con id principal duplicado | 0 |

#### Tipos de datos

| Columna | Tipo pandas |
| --- | --- |
| seller_id | str |
| seller_zip_code_prefix | int64 |
| seller_city | str |
| seller_state | str |

#### Nulos por columna

| Columna | Nulos | % |
| --- | --- | --- |
| seller_id | 0 | 0.00% |
| seller_zip_code_prefix | 0 | 0.00% |
| seller_city | 0 | 0.00% |
| seller_state | 0 | 0.00% |

### product_category_name_translation.csv

| Metrica | Valor |
| --- | --- |
| Filas | 71 |
| Columnas | 2 |
| Filas duplicadas completas sobrantes | 0 |
| Filas duplicadas completas involucradas | 0 |
| Id principal evaluado | product_category_name |
| Filas sobrantes con id principal duplicado | 0 |
| Filas involucradas con id principal duplicado | 0 |

#### Tipos de datos

| Columna | Tipo pandas |
| --- | --- |
| product_category_name | str |
| product_category_name_english | str |

#### Nulos por columna

| Columna | Nulos | % |
| --- | --- | --- |
| product_category_name | 0 | 0.00% |
| product_category_name_english | 0 | 0.00% |

#### Valores frecuentes en estado/categoria

**product_category_name**

| Valor | Frecuencia |
| --- | --- |
| beleza_saude | 1 |
| informatica_acessorios | 1 |
| automotivo | 1 |
| cama_mesa_banho | 1 |
| moveis_decoracao | 1 |
| esporte_lazer | 1 |
| perfumaria | 1 |
| utilidades_domesticas | 1 |
| telefonia | 1 |
| relogios_presentes | 1 |

**product_category_name_english**

| Valor | Frecuencia |
| --- | --- |
| health_beauty | 1 |
| computers_accessories | 1 |
| auto | 1 |
| bed_bath_table | 1 |
| furniture_decor | 1 |
| sports_leisure | 1 |
| perfumery | 1 |
| housewares | 1 |
| telephony | 1 |
| watches_gifts | 1 |

## Integridad entre tablas

| Relacion | Filas evaluadas | Filas no nulas | Filas huerfanas | Valores huerfanos distintos | Ejemplos |
| --- | --- | --- | --- | --- | --- |
| orders.customer_id -> customers.customer_id | 99441 | 99441 | 0 | 0 | - |
| order_items.order_id -> orders.order_id | 112650 | 112650 | 0 | 0 | - |
| order_payments.order_id -> orders.order_id | 103886 | 103886 | 0 | 0 | - |
| order_reviews.order_id -> orders.order_id | 99224 | 99224 | 0 | 0 | - |
| order_items.product_id -> products.product_id | 112650 | 112650 | 0 | 0 | - |
| order_items.seller_id -> sellers.seller_id | 112650 | 112650 | 0 | 0 | - |
| products.product_category_name -> translation.product_category_name | 32951 | 32341 | 13 | 2 | pc_gamer, portateis_cozinha_e_preparadores_de_alimentos |
| customers.customer_zip_code_prefix -> geolocation.geolocation_zip_code_prefix | 99441 | 99441 | 278 | 157 | 72300, 11547, 64605, 72465, 7729, 72904, 35408, 78554, 73369, 8980 |
| sellers.seller_zip_code_prefix -> geolocation.geolocation_zip_code_prefix | 3095 | 3095 | 7 | 7 | 82040, 91901, 72580, 2285, 7412, 71551, 37708 |

## Coherencia temporal en orders

| Regla | Descripcion | Filas | % | Ejemplos order_id |
| --- | --- | --- | --- | --- |
| entrega_cliente_antes_de_compra | order_delivered_customer_date < order_purchase_timestamp | 0 | 0.0 | - |
| delivered_sin_fecha_entrega_cliente | order_status = delivered y order_delivered_customer_date es nula | 8 | 0.01 | 2d1e2d5bf4dc7227b3bfebb81328c15f, f5dd62b788049ad9fc0526e3ad11a097, 2ebdfc4f15f23b91474edf87475f108e, e69f75a717d64fc5ecdfae42b2e8e086, 0d3268bad9b086af767785e3f0fc0133, 2d858f451373b04fb5c984a1cc2defaf, ab7c89dc1bf4a1ead9d6ec1ec8968a84, 20edc82cf5400ce95e1afacc25798b31 |
| aprobacion_antes_de_compra | order_approved_at < order_purchase_timestamp | 0 | 0.0 | - |
| transportista_antes_de_aprobacion | order_delivered_carrier_date < order_approved_at | 1359 | 1.37 | dcb36b511fcac050b97cd5c05de84dc3, 688052146432ef8253587b930b01a06d, 58d4c4747ee059eeeb865b349b41f53a, 412fccb2b44a99b36714bca3fef8ad7b, 56a4ac10a4a8f2ba7693523bb439eede, 32e4fa9bb468884309b58b9348de70c3, 4df92d82d79c3b52c7138679fa9b07fc, 16e38caa92e342c7780f68832f832d4d, b9afddbdcfadc9a87b41a83271c3e888, 6051e6d3da9a50b7325cbe9c81025062 |
| entrega_cliente_antes_de_transportista | order_delivered_customer_date < order_delivered_carrier_date | 23 | 0.02 | a1abeb653a4d4cd1e142ccb8c82cd069, 383aa8b2724fe452d9ccd9934a8c628b, cb1134f9010d242e9515ad1c78ec0c39, dceb62e8fa94b46006c9554fed743df0, 5f9d46795c3126674e52becb3a1a517f, 8c78d01de3a9009e23d6877a7cc9be20, b27af682321527a6349f1761eb3f360c, 1cc3ae63caffff2d6c3ee3e78e074acf, e37f11cae9985ca58f0b56f268720537, fa3e37584f4fdb1ded0e0de700dfcb4e |
| estimada_antes_de_compra | order_estimated_delivery_date < order_purchase_timestamp | 0 | 0.0 | - |
| no_delivered_con_fecha_entrega_cliente | order_status != delivered y order_delivered_customer_date no es nula | 6 | 0.01 | 1950d777989f6a877539f53795b4c3c3, dabf2b0e35b423f94618bf965fcb7514, 770d331c84e5b214bd9dc70a10b829d0, 8beb59392e21af5eb9547ae1a9938d06, 65d1e226dfaeb8cdc42f665422522d14, 2c45c33d2f9cb8ff8b1c86cc28c11c30 |
| delivered_sin_fecha_transportista | order_status = delivered y order_delivered_carrier_date es nula | 2 | 0.0 | 2aa91108853cecb43c84a5dc5b277475, 2d858f451373b04fb5c984a1cc2defaf |
| delivered_sin_fecha_aprobacion | order_status = delivered y order_approved_at es nula | 14 | 0.01 | e04abd8149ef81b95221e88f6ed9ab6a, 8a9adc69528e1001fc68dd0aaebbb54a, 7013bcfc1c97fe719a7b5e05e61c12db, 5cf925b116421afa85ee25e99b4c34fb, 12a95a3c06dbaec84bcfb0e2da5d228a, c1d4211b3dae76144deccd6c74144a88, d69e5d356402adc8cf17e08b5033acfb, d77031d6a3c8a52f019764e68f211c69, 7002a78c79c519ac54022d4f8a65e6e8, 2eecb0d85f281280f79fa00f9cec1a95 |
