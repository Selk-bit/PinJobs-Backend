# Generated by Django 5.1.2 on 2025-01-02 02:08

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('candidates', '0037_remove_jobsearch_status_jobsearch_is_applied'),
    ]

    operations = [
        migrations.CreateModel(
            name='JobClick',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('clicked_at', models.DateTimeField(auto_now_add=True)),
                ('candidate', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='candidates.candidate')),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='candidates.job')),
            ],
            options={
                'unique_together': {('job', 'candidate')},
            },
        ),
        migrations.AddField(
            model_name='job',
            name='clicked_by',
            field=models.ManyToManyField(related_name='clicked_jobs', through='candidates.JobClick', to='candidates.candidate'),
        ),
    ]
