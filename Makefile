APP_DIR = smart-meme

clean_all: clean_images clean_cache
	rm -rf $APP_DIR/.venv

clean_images:
	rm -f ${APP_DIR}/audio.mp3 ${APP_DIR}/captioned_image.jpg ${APP_DIR}/original.jpg

clean_cache: 
	rm -rf ${APP_DIR}/src/__pycache__

deploy:
	aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin 434834777527.dkr.ecr.eu-west-1.amazonaws.com
	docker build -t smart-meme:${TAG} .
	docker tag smart-meme:${TAG} 434834777527.dkr.ecr.eu-west-1.amazonaws.com/smart-meme:${TAG}
	docker push 434834777527.dkr.ecr.eu-west-1.amazonaws.com/smart-meme:${TAG}