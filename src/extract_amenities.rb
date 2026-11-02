require "fileutils"

area = "budapest"
osm_file = "budapest-260802.osm.pbf"

categories = ["amenity", "leisure", "office", "shop", "tourism"]
categories.each do |category|
    puts category
    FileUtils.mkdir_p "../data/osm/#{area}/amenities/"
    %x(osmium tags-filter -o ../data/osm/#{area}/amenities/#{category}.xml ../data/osm/#{area}/#{osm_file} nwr/#{category})
    %x(osmium export ../data/osm/#{area}/amenities/#{category}.xml -o ../data/osm/#{area}/amenities/#{category}.geojson -f geojson --attributes type,id --geometry-types point,polygon)
    File.delete "../data/osm/#{area}/amenities/#{category}.xml"
end
