# Generated by Django 5.2 on 2025-06-26 12:32

import rawdocs.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rawdocs", "0002_create_roles"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="rawdocument",
            name="owner",
        ),
        migrations.AlterField(
            model_name="rawdocument",
            name="file",
            field=models.FileField(upload_to=rawdocs.models.pdf_upload_to),
        ),
    ]
