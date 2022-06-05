import boto3

class MemeData:

    def __init__(self, region='eu-west-1') -> None:
        self.db = boto3.resource('dynamodb', region_name=region)
        self.s3 = boto3.resource('s3', region_name=region)

    def add_new_meme(self, file_name, file_data, bucket, region):
        extra_args={'ACL':'public-read', 'CacheControl' : 'max-age=0'}
        self.s3.Bucket(bucket).upload_fileobj(file_data, file_name, ExtraArgs=extra_args)
        table = self.db.Table('Memes')
        response = table.put_item(
            Item={
                'Name': file_name,
                'processed': False,
                'original_image_public_url': f"https://{bucket}.s3.{region}.amazonaws.com/{file_name}",
                'processed_image_public_url': '',
                'caption' : '',
                'caption_language':'',
                'mp3_bucket_url':''
            }
        )

    def get_all_memes(self):
        table = self.db.Table('Memes')
        response = table.scan()
        memes = response['Items']
        return memes

    def update_meme_audio(self, original_file_name, audio, bucket, region):
        extra_args={'ACL':'public-read', 'CacheControl' : 'max-age=0'}
        self.s3.Bucket(bucket).upload_fileobj(audio['AudioStream'], f"audio/{original_file_name}", ExtraArgs=extra_args)
        table = self.db.Table('Memes')
        table.update_item(
            Key={
                'Name': original_file_name
            },
            UpdateExpression='SET #audio = :audio',
            ExpressionAttributeValues={
                ':audio': f"https://{bucket}.s3.{region}.amazonaws.com/audio/{original_file_name}"
            },
            ExpressionAttributeNames={
              "#audio" : "mp3_bucket_url",
            },
            ReturnValues="UPDATED_NEW"
        )

    def update_meme_caption(self, meme_file_name, original_file_name, caption, caption_language, label, bucket, region) -> None:
        # Upload meme to bucket
        self.s3.Bucket(bucket).upload_file(meme_file_name, f"processed/{original_file_name}", ExtraArgs={'ACL':'public-read', 'CacheControl' : 'max-age=0'})

        # Update image metadata in DynamoDB
        table = self.db.Table('Memes')
        table.update_item(
            Key={
                'Name': original_file_name
            },
            UpdateExpression='SET #proc = :proc, caption = :caption, #procimg = :procimg, #captionlang = :captionlang, #label = :label',
            ExpressionAttributeValues={
                ':proc': True,
                ':caption': caption,
                ':captionlang' : caption_language,
                ':procimg': f"https://{bucket}.s3.{region}.amazonaws.com/processed/{original_file_name}",
                ':label': label,
                
            },
            ExpressionAttributeNames={
              "#proc": "processed",
              "#procimg" : "processed_image_public_url",
              '#captionlang' : "caption_language",
              '#label' : "selected_label"
            },
            ReturnValues="UPDATED_NEW"
        )

        