#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import (
    print_function, unicode_literals, division, absolute_import)

from datetime import datetime
import re
import os
from os.path import join, basename
import json
from collections import defaultdict


def process_text(message, users_map):
    emojis = []
    user_mentions = []

    def special(matchobj):
        match = matchobj.group(0)

        if match[0] == ':':
            emojis.append(match[1:-1])
            return '__' + match[1:-1] + '__'
        elif match[:2] == '<@':
            user_id = match[2:-1]
            if (user_id == 'USLACKBOT'):
                user = 'slackbot'
            else:
                user = users_map[user_id]['name']
            user_mentions.append(user)
            return user
        return ''

    message = re.sub(r'<.*?>|:[a-z0-9_]*?:', special, message)

    return {
        'text': message,
        'emojis': emojis,
        'user_mentions': user_mentions,
    }


def parsed_user(users_file_path):
    users_data = json.loads(open(users_file_path, 'r').read())

    for raw_user in users_data:
        yield {
            'id': raw_user['id'],
            'name': raw_user.get('name'),
        }


def parsed_message(messages_file_path, users_map=None):
    messages_data = json.loads(open(messages_file_path, 'r').read())

    for raw_message in messages_data:
        if raw_message.get('type') != 'message':
            continue

        if not raw_message.get('subtype'):
            user = raw_message['user']
            if users_map and users_map.get(user):
                user = users_map[user]['name']

            reactions = []
            for r in raw_message.get('reactions', []):
                for i, id in enumerate(r['users']):
                    if id in users_map.keys():
                        r['users'][i] = users_map[id]['name']
                reactions.append(r)

            attachments = []
            for a in raw_message.get('attachments', []):
                attachments.append({
                    'service_name': a.get('service_name'),
                    'title': a.get('title'),
                    'text': a.get('text'),
                    'from_url': a.get('from_url'),
                })

            d = {
                'user': user,
                'ts': datetime.utcfromtimestamp(float(raw_message['ts'])),
                'reactions': reactions,
                'attachments': attachments,
            }
            d.update(process_text(raw_message['text'], users_map))
            yield d


def parse_log(directory=None):
    if directory is None:
        directory = os.environ['SLP_SLACK_LOG_DIR']

    # Parse users
    users_file_path = join(directory, 'users.json')
    users = {}
    for u in parsed_user(users_file_path):
        users[u['id']] = u

    # Parse messages
    messages = defaultdict(list)
    for root, dirs, files in os.walk(directory):
        channel_name = basename(root)
        for file_name in files:
            if not re.match(r'\d{4}-\d{2}-\d{2}\.json', file_name):
                continue

            messages_iter = parsed_message(messages_file_path=join(root, file_name),
                                           users_map=users)
            if messages_iter:
                messages[channel_name].extend(messages_iter)

    return {
        'users': users,
        'messages': messages,
    }
