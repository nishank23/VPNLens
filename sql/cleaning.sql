SELECT time_zone,NULLIF(time_zone,'-') as cleaned_time_zone,zip_code,NULLIF(zip_code,'-') as cleaned_zip_code,city_name,NULLIF(city_name,'-') as cleaned_city_name,region_name,NULLIF(region_name,'-') as cleaned_region_name,country_name,NULLIF(country_name,'-') as cleaned_country_name,country_code, NULLIF(country_code,'-') as cleaned_country_code
FROM RAW_IP2LOCATION WHERE country_name ='-' 
OR country_code = '-' 
OR time_zone = '-'
OR zip_code = '-'
OR city_name = '-'
OR region_name = '-'
;