# -*- coding: utf-8 -*-
import csv
import codecs, cStringIO


class UTF8Recoder:
    """
    Iterator that reads an encoded stream and reencodes the input to UTF-8
    """
    def __init__(self, f, encoding):
        self.reader = codecs.getreader(encoding)(f)

    def __iter__(self):
        return self

    def next(self):
        return self.reader.next().encode("utf-8")

class UnicodeReader:
    """
    A CSV reader which will iterate over lines in the CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        f = UTF8Recoder(f, encoding)
        self.reader = csv.reader(f, dialect=dialect, **kwds)

    def next(self):
        row = self.reader.next()
        return [unicode(s, "utf-8") for s in row]

    def __iter__(self):
        return self

class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([s.encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)



def create_module_user(user, ml, slack, f):
    # Create a new classifier
    res = ml.classifiers.create('slack_' + user)

    # Get the id of the new module
    module_id = res.result['classifier']['hashed_id']

    # Get the id of the root node
    res = ml.classifiers.detail(module_id)
    root_id = res.result['sandbox_categories'][0]['id']

    # Create two new categories on the root node
    res = ml.classifiers.categories.create(module_id, 'no', root_id)
    negative_id = res.result['category']['id']
    res = ml.classifiers.categories.create(module_id, 'yes', root_id)
    positive_id = res.result['category']['id']

    reader = UnicodeReader(f)
    samples = []
    for row in reader:
        if row[1] == 'yes':
            label_id = positive_id
        else:
            label_id = negative_id
        samples.append((row[0], label_id))

    # Now let's upload some samples
    res = ml.classifiers.upload_samples(module_id, samples)

    # Now let's train the module!
    res = ml.classifiers.train(module_id)

    return module_id
