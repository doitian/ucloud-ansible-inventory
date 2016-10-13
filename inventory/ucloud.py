#!/usr/bin/env python

import argparse
import ConfigParser
import os
import re
import hashlib
import httplib
import urlparse
import urllib
import sys
import errno

from time import time
from collections import defaultdict

try:
  import json
except ImportError:
  import simplejson as json

class UCClient:
  def __init__(self, base_url, public_key, private_key):
    self.global_params = { 'PublicKey': public_key }
    self.private_key = private_key
    self.base_url = base_url

    url = urlparse.urlsplit(base_url)
    if url.scheme == 'https':
        self.conn = httplib.HTTPSConnection(url.netloc)
    else:
        self.conn = httplib.HTTPConnection(url.netloc)

  def get(self, uri, params):
    merged_params = dict(self.global_params, **params)
    merged_params["Signature"] = self.sign(merged_params)
    self.conn.request("GET", uri + '?' + urllib.urlencode(merged_params))
    response = json.loads(self.conn.getresponse().read())
    return response

  DATA_SET_NAME_MAP = {
      'UHostInstance': 'UHostSet',
      'UcdnDomain': 'DomainSet'
      }
  BATCH_SIZE = 100

  def describe(self, resource, params):
    offset = 0
    got_count = self.BATCH_SIZE
    data_set_name = self.DATA_SET_NAME_MAP.get(resource, 'DataSet')

    while got_count == self.BATCH_SIZE:
      query = dict({'Action': 'Describe' + resource, 'Limit': offset + self.BATCH_SIZE, 'Offset': offset}, **params)
      offset += self.BATCH_SIZE

      response = self.get('/', query)
      if 'ToaltCount' in response:
        got_count = response['ToaltCount']
      elif 'TotalCount' in response:
        got_count = response['TotalCount']
      else:
        got_count = 0

      if data_set_name in response:
        for item in response[data_set_name]:
          yield item


  def sign(self, params):
    items = params.items()
    items.sort()

    sign_data = ''.join([str(key) + str(value) for key, value in items])
    sign_data = sign_data + self.private_key

    digest = hashlib.sha1()
    digest.update(sign_data)
    return digest.hexdigest()

  def __del__(self):
    self.conn.close()


class UCInventory:
  def _empty_index(self):
    index = defaultdict(list, {'_meta': {'hostvars' : {}}})
    return index

  def __init__(self):
    self.read_settings()
    self.parse_cli_args()
    self.load_inventory()

    if self.args.host:
      host_vars = self.inventory['index']['_meta']['hostvars'][self.args.host]
      data_to_print = host_vars or {}
    else:
      data_to_print = self.inventory['index']

    print self.json_format_dict(data_to_print, True)

  def read_settings(self):
    """ Reads the settings from the ucloud.ini file """

    config = self.config = ConfigParser.RawConfigParser()
    script_file = os.path.realpath(__file__)
    config_dir = os.path.dirname(script_file)
    config_basename = os.path.basename(script_file).rsplit('.', 1)[0] + '.ini'
    config.read('/'.join([config_dir, config_basename]))

    self.region = config.get('ucloud', 'region')
    self.client = UCClient(
        config.get('ucloud', 'base_url'),
        config.get('ucloud', 'public_key'),
        config.get('ucloud', 'private_key')
        )

    # Cache related
    self.cache_path = config.get('cache', 'path')
    cache_dir = os.path.dirname(self.cache_path)
    try:
      os.makedirs(cache_dir)
    except OSError as exc:
      if exc.errno == errno.EEXIST and os.path.isdir(cache_dir):
        pass
      else: raise

    self.cache_max_age = config.getint('cache', 'max_age')


  def is_cache_valid(self):
    """ Determines if the cache files have expired, or if it is still valid """

    if os.path.isfile(self.cache_path):
      mod_time = os.path.getmtime(self.cache_path)
      current_time = time()
      return (mod_time + self.cache_max_age) > current_time
    else:
      return False


  def build_inventory(self):
    index = self._empty_index()
    self.add_uhosts(index)
    self.add_ulbs(index)
    self.add_ucdns(index)

    return { 'index': index }


  def add_uhosts(self, index):
    for uhost in self.client.describe('UHostInstance', { 'Region': self.region }):
      uhost = self.extract_ips(uhost)
      safe_name = self.to_safe(uhost['Name'])
      options = self.item_options('uhost', safe_name, uhost)
      inventory_name = self.to_safe(options['name'] % uhost)
      for g in options['group'].split(','):
        index[g].append(inventory_name)
      for tag in uhost['Tag'].split(','):
        for expanded_tag in (options['tag'] % { 'Tag': tag.strip() }).split(','):
          if len(expanded_tag) > 0:
            index[self.to_safe(expanded_tag)].append(inventory_name)

      ssh_options = self.ssh_options(options, uhost)
      index['_meta']['hostvars'][inventory_name] = dict(ssh_options, ucloud = uhost)


  def add_ulbs(self, index):
    for ulb in self.client.describe('ULB', { 'Region': self.region }):
      ulb = self.extract_ips(ulb)
      safe_name = self.to_safe(ulb['Name'])
      options = self.item_options('ulb', safe_name, ulb)
      inventory_name = self.to_safe(options['name'] % ulb)
      for g in options['group'].split(','):
        index[g].append(inventory_name)
      ssh_options = self.ssh_options(options, ulb)
      index['_meta']['hostvars'][safe_name] = dict(ssh_options, ucloud = ulb)


  def add_ucdns(self, index):
    for ucdn in self.client.describe('UcdnDomain', { 'Region': self.region }):
      safe_name = self.to_safe(ucdn['Domain'])
      options = self.item_options('ucdn', safe_name, ucdn)
      inventory_name = self.to_safe(options['name'] % ucdn)
      for g in options['group'].split(','):
        index[g].append(inventory_name)

      ssh_options = self.ssh_options(options, ucdn)

      index['_meta']['hostvars'][safe_name] = dict(ssh_options, ucloud = ucdn)


  def extract_ips(self, instance):
    if 'IPSet' in instance:
      for ip in instance['IPSet']:
        if 'IP' in ip:
          instance[ip['Type'] + 'IP'] = ip['IP']
        else:
          instance[ip['OperatorName'] + 'IP'] = ip['EIP']
      instance['PublicIP'] = instance.get('BgpIP') or instance.get('InternationalIP') or instance.get('TelecomIP') or instance.get('UnicomIP')

    return instance

  def item_options(self, kind, name, instance):
    options = dict(self.config.items(kind))
    specific_section = '.'.join([kind, name])
    if self.config.has_section(specific_section):
      options.update(self.config.items(specific_section))

    return options

  def ssh_options(self, options, instance):
    return {
        'ansible_ssh_user': options['user'] % instance,
        'ansible_ssh_host': options['host'] % instance,
        'ansible_ssh_port': options['port'] % instance
        }


  def load_inventory(self):
    if self.args.refresh_cache or not self.is_cache_valid():
      self.inventory = self.build_inventory()
      self.write_cache()
    else:
      self.read_cache()


  def write_cache(self):
    json_data = self.json_format_dict(self.inventory, True)
    cache = open(self.cache_path, 'w')
    cache.write(json_data)
    cache.close()


  def read_cache(self):
    cache = open(self.cache_path, 'r')
    json_data = cache.read()
    self.inventory = json.loads(json_data)


  def to_safe(self, word):
    ''' Converts 'bad' characters in a string to underscores so they can be
    used as Ansible groups '''

    return re.sub("[^A-Za-z0-9\-]", "_", word)


  def parse_cli_args(self):
    ''' Command line argument processing '''

    parser = argparse.ArgumentParser(description='Produce an Ansible Inventory file based on UCLOUD')
    parser.add_argument('--list', action='store_true', default=True,
                        help='List instances (default: True)')
    parser.add_argument('--host', action='store',
                        help='Get all the variables about a specific instance')
    parser.add_argument('--refresh-cache', action='store_true', default=False,
                        help='Force refresh of cache by making API requests to UCLOUD (default: False - use cache files)')
    self.args = parser.parse_args()


  def json_format_dict(self, data, pretty=False):
    if pretty:
      return json.dumps(data, sort_keys=True, indent=2)
    else:
      return json.dumps(data)


UCInventory()

