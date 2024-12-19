# Generated by Django 5.1.2 on 2024-12-19 05:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('candidates', '0033_alter_job_title'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cv',
            name='generated_pdf',
            field=models.FileField(blank=True, null=True, upload_to='Cvs/pdf/'),
        ),
        migrations.AlterField(
            model_name='cv',
            name='original_file',
            field=models.FileField(blank=True, null=True, upload_to='Cvs/original/'),
        ),
        migrations.AlterField(
            model_name='cv',
            name='thumbnail',
            field=models.ImageField(blank=True, null=True, upload_to='Cvs/thumbnails/'),
        ),
    ]