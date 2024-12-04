"""
Django settings for pinjobs project.

Generated by 'django-admin startproject' using Django 5.1.2.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

from pathlib import Path
from dotenv import load_dotenv
import os
from datetime import timedelta
from celery.schedules import crontab

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv()
EXTERNAL_API_URL = os.getenv('EXTERNAL_API_URL')
PROXYCURL_API_KEY = os.getenv('PROXYCURL_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-2xcxt#4wfn87%_9(1$^3w@(7+ynt*9_9(f(%2tvdcoai97$q&u'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["pinjobs-backend.onrender.com", "https://pinjobs-backendv2.onrender.com", "127.0.0.1", ]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'candidates',
    'django_json_widget',
    'rest_framework',
    'django_celery_results',
    'django_celery_beat',
    'corsheaders',
    'channels',
    'drf_yasg',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),  # Set token expiration to 1 day
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
]

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

ROOT_URLCONF = 'pinjobs.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'pinjobs.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'OPTIONS': {'charset': 'utf8mb4'},
#         'NAME': 'pinjobs',  # Replace with your database name
#         'USER': 'root',  # Replace with your database username
#         'PASSWORD': '',  # Replace with your database password
#         'HOST': 'localhost',  # Replace if your MySQL server is hosted elsewhere
#         'PORT': '3306',  # Default MySQL port
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'OPTIONS': {'charset': 'utf8mb4'},
        'NAME': 'pinjobs',  # Replace with your database name
        'USER': 'salim',  # Replace with your database username
        'PASSWORD': 'salim',  # Replace with your database password
        'HOST': 'mysql-mq46',  # Replace if your MySQL server is hosted elsewhere
        'PORT': '3306',  # Default MySQL port
    }
}
os.environ["PATH"] += os.pathsep + os.path.join(os.getenv("HOME"), "bin")


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


CELERY_BROKER_URL = 'rediss://red-cstg411u0jms73ek3hs0:q0TgQSpRDJLrusS5PTEKUOIHnlWtm5kL@oregon-redis.render.com:6379'  # Use your Redis server config
CELERY_RESULT_BACKEND = 'django-db'  # To store task results in the Django database
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers.DatabaseScheduler'  # For periodic tasks
CELERY_BEAT_SCHEDULE = {
    'run-scheduled-job-scraping': {
        'task': 'pinjobs.tasks.scheduled_job_scraping',
        'schedule': crontab(minute=0),
    },
}
CELERY_TIMEZONE = 'UTC'


EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'salim.elkellouti@etu.uae.ac.ma'
EMAIL_HOST_PASSWORD = 'monsef2018'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

ASGI_APPLICATION = "pinjobs.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}

SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'description': 'JWT Authorization header using the Bearer scheme. Example: "Authorization: Bearer {token}"',
            'name': 'Authorization',
            'in': 'header',
        }
    },
    'USE_SESSION_AUTH': False,
}