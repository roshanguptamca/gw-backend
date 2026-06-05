"""
Migration 0006: Encrypt subject and message fields at rest.

Changes:
  - EmailReminder.subject: CharField(max_length=250) → EncryptedTextField (TEXT column)
  - EmailReminder.message: TextField → EncryptedTextField (TEXT column, same DB type)

The DB column type for subject changes from VARCHAR(250) to TEXT so that
the AES-256-GCM ciphertext (which is longer than the plaintext) fits without
truncation. The max_length=250 constraint is now enforced in the serializer.
"""

import apps.future_wise.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("future_wise", "0005_seed_reminder_channels"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emailreminder",
            name="subject",
            field=apps.future_wise.fields.EncryptedTextField(),
        ),
        migrations.AlterField(
            model_name="emailreminder",
            name="message",
            field=apps.future_wise.fields.EncryptedTextField(),
        ),
    ]
