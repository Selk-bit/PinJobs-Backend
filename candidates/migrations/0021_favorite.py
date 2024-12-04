# Generated by Django 5.1.2 on 2024-12-02 18:18

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('candidates', '0020_cv_cv_type_cv_job_alter_cv_candidate_alter_cvdata_cv'),
    ]

    operations = [
        migrations.CreateModel(
            name='Favorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorites', to='candidates.candidate')),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='favorited_by', to='candidates.job')),
            ],
            options={
                'unique_together': {('candidate', 'job')},
            },
        ),
    ]
