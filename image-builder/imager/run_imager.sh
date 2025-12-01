docker run --rm -d --name nginx\
    -v "$(PWD)/nginx/default.conf":/etc/nginx/conf.d/default.conf \
    -v "$(PWD)/../deploy":/files \
    -p 8080:80 \
    nginx:alpine
"/Applications/Raspberry Pi Imager.app/Contents/MacOS/rpi-imager" --repo "$(pwd)/sat1-os-list.json"
docker stop nginx
    
