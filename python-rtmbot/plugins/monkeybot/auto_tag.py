# -*- coding: utf-8 -*-
import json
from random import randint

from slack_parser import parse_log

from create_modules import UnicodeReader, UnicodeWriter


MESSAGE_DISTANCE = 120
CONVERSATION_LEVEL = True
IS_MULTILABEL = False
IS_MULTIFEATURE = False

d = {}
conversations = []
stats = {
    '#messages': 0,
    '#conversations': 0,
    '#conversations_per_length': {},
    'avg_messages_per_conv': 0
}


def create_conversation(start):
    return {'start': start, 'messages': []}


def is_in_conversation(message, conv):
    if len(conv['messages']) == 0:
        return True
    return (message['ts'] - conv['messages'][-1]['ts']).total_seconds() <= MESSAGE_DISTANCE


def extract_conversations(data):
    for channel in data:
        print channel
        # initialize first conversation with first message of the channel
        if not len(data[channel]):
            continue
        current_conv = create_conversation(data[channel][0]['ts'])

        for message in data[channel]:
            stats['#messages'] += 1
            if is_in_conversation(message, current_conv):
                current_conv['messages'].append(message)
            else:
                conversations.append((current_conv, channel))
                stats['#conversations'] += 1
                if len(current_conv['messages']) in stats['#conversations_per_length']:
                    stats['#conversations_per_length'][len(current_conv['messages'])] += 1
                else:
                    stats['#conversations_per_length'][len(current_conv['messages'])] = 1
                stats['avg_messages_per_conv'] += len(current_conv['messages'])
                current_conv = create_conversation(message['ts'])

    stats['avg_messages_per_conv'] /= stats['#conversations']
    print stats
    return conversations


def extract_features_message(message, channel):

    attachment_content = ''
    if 'attachments' in message:
        for attachment in message['attachments']:

            attachment_content += ((attachment['service_name'] or ' ') + ' ' +
            (attachment['title'] or ' ') + ' ' +
            (attachment['text'] or ' '))

    users_reacted = ''
    if 'reactions' in message:
        for r in message['reactions']:
            for user in r['users']:
                users_reacted += user

    return {
        # title + text (link) or text (message)
        'author': message['user'],
        'text_content': message['text'],
        'channel': channel,
        'text_attachment_content': attachment_content,
        'text_user_mentions': ' '.join(message['user_mentions']),
        'text_users_reacted': users_reacted
    }


def extract_features_conv(conv, channel):

    d = {
        'text_authors': '',
        'channel': channel,
        'text_content': '',
        'text_user_mentions': '',
        'text_users_reacted': ''
    }

    authors = set([])

    for message in conv['messages']:
        message_features = extract_features_message(message, channel)
        if not message_features['text_content'] and not message_features['text_attachment_content']:
            continue
        #d['text_authors'] += ' ' + message_features['author']
        authors.add(message_features['author'])
        d['text_content'] += ' ' + message_features['text_content'] + ' ' + message_features['text_attachment_content']
        d['text_user_mentions'] += ' ' + message_features['text_user_mentions']
        d['text_users_reacted'] += ' ' + message_features['text_users_reacted']

    d['text_authors'] = ' '.join(authors)
    return d


def extract_tags_conv(conv):
    tags = set([])

    for message in conv['messages']:
        # users that sent a message in the conversation
        tags.add(message['user'])

        # users that reacted to a message in the conversation
        for r in message['reactions']:
            for user in r['users']:
                tags.add(user)

        # users mentioned in a message in the conversation
        for user in message['user_mentions']:
            tags.add(user)

    return tags


def extract_tags_message(message):
    tags = set([])

    # users that sent a message in the conversation
    tags.add(message['user'])

    # users that reacted to a message in the conversation
    for r in message['reactions']:
        for user in r['users']:
            tags.add(user)

    # users mentioned in a message in the conversation
    for user in message['user_mentions']:
        tags.add(user)

    return tags


if __name__ == "__main__":

    log = parse_log('export')
    data = log['messages']

    user_neg = {}

    if IS_MULTILABEL:
        f = open('training_set_content.csv', 'w')
        writer = UnicodeWriter(f)
    else:
        writers = {}
        files = []
        for user in log['users'].values():
            f = open('users_data/training_set_' + user['name'] + '.csv', 'w')
            writers[user['name']] = UnicodeWriter(f)
            files.append(f)

            user_neg[user['name']] = {'neg': [], 'pos': 0}


    if CONVERSATION_LEVEL:
        conversations = extract_conversations(data)
        for conv, channel in conversations:
            features = extract_features_conv(conv, channel)

            if features['text_content'] == '':
                print "Empty conversation:"
                print features
                continue
            if IS_MULTIFEATURE:
                del features['text_user_mentions']
                del features['text_users_reacted']
                text = json.dumps(features, ensure_ascii=False)
            else:
                text = ' '.join([features['text_content'], channel])
            tags = extract_tags_conv(conv)

            if IS_MULTILABEL:
                writer.writerow([text, ':'.join(tags)])
            else:
                for user in log['users'].values():
                    if user['name'] in tags:
                        writers[user['name']].writerow([text, 'yes'])
                        user_neg[user['name']]['pos'] += 1
                    else:
                        user_neg[user['name']]['neg'].append(text)

        for name in user_neg:
            print name, user_neg[name]['pos'], len(user_neg[user['name']]['neg'])

            for i in range(user_neg[name]['pos']):
                j = randint(0, len(user_neg[name]['neg']) - 1)
                text = user_neg[name]['neg'].pop(j)
                writers[name].writerow([text, 'no'])

    else:
        for channel in data:
            print channel
            for message in data[channel]:
                features = extract_features_message(message, channel)
                text = json.dumps(features)
                tags = extract_tags_message(message)
            writer.writerow([text, ':'.join(tags)])

    if IS_MULTILABEL:
        f.close()
    else:
        for f in files:
            f.close()
