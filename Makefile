APP_DIR = smart-meme

clean_all: clean_images clean_cache

clean_images:
	rm -f ${APP_DIR}/audio.mp3 ${APP_DIR}/captioned_image.jpg ${APP_DIR}/original.jpg

clean_cache: 
	rm -rf ${APP_DIR}/app/__pycache__