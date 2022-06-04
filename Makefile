APP_DIR = smart-meme

clean_images:
	rm -f ${APP_DIR}/audio.mp3 ${APP_DIR}/captioned_image.jpg ${APP_DIR}/original.jpg

clean_all: clean_images
	rm -rf ${APP_DIR}/__pycache__ ${APP_DIR}/.venv