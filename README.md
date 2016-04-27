Description
-----------



Instructions
------------

1) Export and import Slack historical data

Team Settings -> Import/Export Data -> Export -> Start Export

After the export is ready for download, you will be able to download a zipfile

Extract the contents of the zipfile into the export folder

Run the following command:

python auto_tag.py

This will create the training sets for each user in your Slack team. It will generate a csv file for each user in the users_data folder.
