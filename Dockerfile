
FROM python:3.9-slim-buster

WORKDIR /app

RUN apt-get update && apt-get install -y tk

COPY ./smart-meme/requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY ./smart-meme .

CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0"]