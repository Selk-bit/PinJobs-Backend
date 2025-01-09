from storages.backends.s3boto3 import S3Boto3Storage


class MediaStorage(S3Boto3Storage):
    def get_available_name(self, name, max_length=None):
        return name
