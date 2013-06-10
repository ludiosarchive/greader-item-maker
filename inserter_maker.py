import os
import sys
import urllib
import subprocess
from struct import pack, unpack

# https://code.google.com/p/leveldb-py/
import leveldb

num_urls_in_item = 200
# The maximum number of bytes we can append to a file without
# corruption, assuming that there is no locking present.
max_safe_file_append_length = 4096


def try_makedirs(p):
	try:
		os.makedirs(p)
	except OSError:
		pass


def write_item(items_root, item_id, encoded_urls):
	item_name = str(item_id).zfill(10)
	assert encoded_urls, encoded_urls
	assert len(item_name) == 10, item_name
	fdir = os.path.join(items_root, item_name[0:6])
	try_makedirs(fdir)
	fname = os.path.join(fdir, item_name)
	assert not os.path.exists(fname), fname
	assert not os.path.exists(fname + ".gz"), fname
	with open(fname + ".tmp", "wb") as f:
		f.write("\n".join(encoded_urls) + "\n")
	# TODO: use Python gzip module to avoid subprocess spawning cost
	subprocess.call(["gzip", "-9", fname + ".tmp"])
	os.rename(fname + ".tmp.gz", fname + ".gz")


def write_new_encoded_urls(urls, uninserted_file):
	"""
	Write out the encoded URLs that we haven't inserted into the database
	yet, because we didn't have enough URLs for a work item.
	"""
	with open(uninserted_file, "ab") as f:
		for u in urls:
			if len(u) + 1 > max_safe_file_append_length:
				print "Failed to write out %r to %r; URL is too long" % (u, uninserted_file)
				continue
			f.write(u + "\n")


def encode_item_ids(ids):
	return "".join(pack("<i", n) for n in ids)


def decode_item_ids(ids):
	return unpack("<i", ids)


def reversed_encoded_url(url):
	# TODO XXX ENCODE THESE URLs into reverse.domain.format
	return url


def insert_new_encoded_urls(db, new_encoded_urls):
	assert len(new_encoded_urls) == num_urls_in_item, new_encoded_urls
	packed_next_item_id = db.get("$next_item_id$", fill_cache=False)
	assert len(packed_next_item_id) == 4, packed_next_item_id
	next_item_id, = unpack("<i", packed_next_item_id)

	batch = db.newBatch()
	for u in new_encoded_urls:
		db.putTo(batch, reversed_encoded_url(u), packed_next_item_id)
	db.putTo(batch, "$next_item_id$", pack("<i", next_item_id + 1))
	db.write(batch)

	# The item we write has the normal *not* reversed URLs


	new_encoded_urls.clear()


def maybe_insert_new_encoded_urls(db, new_encoded_urls):
	assert len(new_encoded_urls) <= num_urls_in_item, new_encoded_urls
	if len(new_encoded_urls) == num_urls_in_item:
		insert_new_encoded_urls(db, new_encoded_urls)


def open_db(db_path):
	return leveldb.DB(
		db_path, bloom_filter_size=16, create_if_missing=True,
		write_buffer_size=(64*1024*1024), block_cache_size=(128*1024*1024))


def insert_urls(db, inputf, new_encoded_urls):
	for n, feed_url in enumerate(inputf):
		if n % 10000 == 0:
			print n
		feed_url = feed_url.rstrip()
		if not feed_url:
			continue
		try:
			feed_url.decode('ascii')
		except UnicodeDecodeError:
			print "Failed to decode as ascii; skipping %r" % (feed_url,)
			continue
		assert feed_url.startswith("http://") or feed_url.startswith("https://"), feed_url
		encoded_url = urllib.quote_plus(feed_url)
		if encoded_url in new_encoded_urls:
			# No need to even hit DB in this case
			continue
		if db.has(reversed_encoded_url(encoded_url)):
			continue
		new_encoded_urls.add(encoded_url)

		print encoded_url, "queued for insertion"

		maybe_insert_new_encoded_urls(db, new_encoded_urls)

	maybe_insert_new_encoded_urls(db, new_encoded_urls)


def main():
	db_path = sys.argv[1]
	uninserted_file = sys.argv[2]

	db = open_db(db_path)
	new_encoded_urls = set()

	try:
		insert_urls(db, sys.stdin, new_encoded_urls)
	finally:
		write_new_encoded_urls(new_encoded_urls, uninserted_file)
		db.close()



if __name__ == '__main__':
	main()
