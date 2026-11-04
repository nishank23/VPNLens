-- BEGIN;
TRUNCATE Table ip2location;

-- A plain transform clears the old release marker. The DB-IP loader sets
-- its new marker after validating the transformed row count.
DO $$
BEGIN
    IF to_regclass('dbip_geolocation_release') IS NOT NULL THEN
        DELETE FROM dbip_geolocation_release;
    END IF;
END;
$$;

INSERT INTO ip2location(
	ip_from,
	ip_to,
	country_code, 
	country_name,
	region_name, 
	city_name,
	latitude,
	longitude,
	zip_code,
	time_zone,
	ip_range
)
SELECT ip_from, ip_to,NULLIF(country_code,'-') as country_code,
					NULLIF(country_name,'-') as country_name, 
					NULLIF(region_name,'-') as region_name, 
					NULLIF(city_name,'-') as city_name ,
					latitude,longitude, 
					NULLIF(zip_code,'-') as zip_code , 
					NULLIF(time_zone,'-') as time_zone,
					int8range(ip_from, ip_to, '[]') AS ip_range
from raw_ip2location;