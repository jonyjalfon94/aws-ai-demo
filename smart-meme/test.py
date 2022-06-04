import boto3

BUCKET = "rekognition-demo-sela"
KEY = "HIMYM.jpg"


def upload_image():
    s3 = boto3.resource('s3')
    s3.Bucket(BUCKET).upload_file(KEY, f"images/{KEY}")

def detect_labels(bucket, key, max_labels=10, min_confidence=90, region="eu-west-1"):
	rekognition = boto3.client("rekognition", region)
	response = rekognition.detect_labels(
		Image={
			"S3Object": {
				"Bucket": bucket,
				"Name": key,
			}
		},
		MaxLabels=max_labels,
		MinConfidence=min_confidence,
	)
	return response['Labels']




def main():
	upload_image()
	for label in detect_labels(BUCKET, f"images/{KEY}", min_confidence=90):
		print("{Name} - {Confidence}%".format(**label))
		# detect_labels(BUCKET, f"images/{KEY}", max_labels=10, min_confidence=90, region="eu-west-1")

main()
