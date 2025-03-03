# coding: utf-8
from __future__ import unicode_literals

import re

from .common import InfoExtractor
from ..utils import (
    ExtractorError,
    int_or_none,
    try_get,
    url_or_none,
    urlencode_postdata,
)


class HiDiveIE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?hidive\.com/stream/(?P<title>[^/]+)/(?P<key>[^/?#&]+)'
    # Using X-Forwarded-For results in 403 HTTP error for HLS fragments,
    # so disabling geo bypass completely
    _GEO_BYPASS = False
    _NETRC_MACHINE = 'hidive'
    _LOGIN_URL = 'https://www.hidive.com/account/login'

    _TESTS = [{
        'url': 'https://www.hidive.com/stream/the-comic-artist-and-his-assistants/s01e001',
        'info_dict': {
            'id': 'the-comic-artist-and-his-assistants/s01e001',
            'ext': 'mp4',
            'title': 'the-comic-artist-and-his-assistants/s01e001',
            'series': 'the-comic-artist-and-his-assistants',
            'season_number': 1,
            'episode_number': 1,
        },
        'params': {
            'skip_download': True,
        },
        'skip': 'Requires Authentication',
    }]

    def _real_initialize(self):
        email, password = self._get_login_info()
        if email is None:
            return

        webpage = self._download_webpage(self._LOGIN_URL, None)
        form = self._search_regex(
            r'(?s)<form[^>]+action="/account/login"[^>]*>(.+?)</form>',
            webpage, 'login form')
        data = self._hidden_inputs(form)
        data.update({
            'Email': email,
            'Password': password,
        })
        self._download_webpage(
            self._LOGIN_URL, None, 'Logging in', data=urlencode_postdata(data))

    def _real_extract(self, url):
        mobj = self._match_valid_url(url)
        title, key = mobj.group('title', 'key')
        video_id = '%s/%s' % (title, key)
        webpage = self._download_webpage(url, video_id, fatal=False)
        data_videos = re.findall(r'data-video=\"([^\"]+)\"\s?data-captions=\"([^\"]+)\"', webpage)
        formats = []
        subtitles = {}
        for data_video in data_videos:
            _, _, _, version, audio, _, extra = data_video[0].split('_')
            caption = data_video[1]

            settings = self._download_json(
                'https://www.hidive.com/play/settings', video_id,
                data=urlencode_postdata({
                    'Title': title,
                    'Key': key,
                    'PlayerId': 'f4f895ce1ca713ba263b91caeb1daa2d08904783',
                    'Version': version,
                    'Audio': audio,
                    'Captions': caption,
                    'Extra': extra,
                }))

            restriction = settings.get('restrictionReason')
            if restriction == 'RegionRestricted':
                self.raise_geo_restricted()

            if restriction and restriction != 'None':
                raise ExtractorError(
                    '%s said: %s' % (self.IE_NAME, restriction), expected=True)

            for rendition_id, rendition in settings['renditions'].items():
                m3u8_url = url_or_none(try_get(rendition, lambda x: x['bitrates']['hls']))
                if not m3u8_url:
                    continue
                frmt = self._extract_m3u8_formats(
                    m3u8_url, video_id, 'mp4', entry_protocol='m3u8_native',
                    m3u8_id='%s-%s-%s-%s' % (version, audio, extra, caption), fatal=False)
                for f in frmt:
                    f['language'] = audio
                formats.extend(frmt)

                for cc_file in rendition.get('ccFiles', []):
                    cc_url = url_or_none(try_get(cc_file, lambda x: x[2]))
                    # name is used since we cant distinguish subs with same language code
                    cc_lang = try_get(cc_file, (lambda x: x[1].replace(' ', '-').lower(), lambda x: x[0]), str)
                    if cc_url and cc_lang:
                        subtitles.setdefault(cc_lang, []).append({'url': cc_url})
        self._sort_formats(formats)

        season_number = int_or_none(self._search_regex(
            r's(\d+)', key, 'season number', default=None))
        episode_number = int_or_none(self._search_regex(
            r'e(\d+)', key, 'episode number', default=None))

        return {
            'id': video_id,
            'title': video_id,
            'subtitles': subtitles,
            'formats': formats,
            'series': title,
            'season_number': season_number,
            'episode_number': episode_number,
            'http_headers': {'Referer': url}
        }
