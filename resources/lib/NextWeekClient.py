# # -*- coding: utf-8 -*- 

from utilities import log
import urllib, re, os, copy, xbmc, xbmcgui
import HTMLParser
from stats import results_with_stats
from difflib import SequenceMatcher

class NextWeekClient(object):

	def __init__(self,addon):
		self.server_url = "http://www.nextweek.cz"
		self.addon = addon
		self._t = addon.getLocalizedString

	def download(self,link):

		dest_dir = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile').decode("utf-8")), 'temp')
		dest = os.path.join(dest_dir, "download.tmp")

		log(__name__,'Downloading subtitles from %s' % link)
		res = urllib.urlopen(link)
		
		subtitles_filename = re.search("Content\-Disposition: attachment; filename=\"(.+?)\"",str(res.info())).group(1)
		log(__name__,'Filename: %s' % subtitles_filename)
		subtitles_format = re.search("\.(\w+?)$", subtitles_filename, re.IGNORECASE).group(1)
		log(__name__,"Subs in %s" % subtitles_format)
		
		subtitles_data = res.read()

		log(__name__,'Saving to file %s' % dest)
		zip_file = open(dest,'wb')
		zip_file.write(subtitles_data)
		zip_file.close()

		final_dest = os.path.join(dest_dir, "download." + subtitles_format)

		log(__name__,'Changing filename to %s' % final_dest)
		os.rename(dest, final_dest)

		return final_dest

	def get_tv_show_list(self):
		res = urllib.urlopen(self.server_url + "/titulky/category/1-titulky")
		if not res.getcode() == 200: return None
		tv_shows_content = re.search("<section id=\"content\" class=\"grid-block\">(.+?)</section>", res.read(), re.IGNORECASE | re.DOTALL )
		if tv_shows_content == None: return None

		tv_shows = []
		for tv_show_html in re.findall("<div class=\"pd-subcategory\">(.+?)</div>", tv_shows_content.group(1).decode("utf-8"), re.IGNORECASE | re.DOTALL):
			tv_show_url, tv_show_name = re.search("<a href=\"(.+?)\">(.+?)</a>", tv_show_html, re.IGNORECASE).groups()
			tv_show_with_translation = re.search("(.+?) \(.+?\)",tv_show_name)
			if tv_show_with_translation: tv_show_name = tv_show_with_translation.group(1)
			tv_shows.append({ "url" : tv_show_url, "title": tv_show_name })

		return tv_shows

	def search_show_url(self, title, show_list):
		log(__name__,"Starting search by TV Show: %s" % title)
		if not title: return None

		for threshold_ratio in range(100,50,-5):
			if threshold_ratio == None: return show_list
			tv_show_list = []
			for tv_show in show_list:
				matcher = SequenceMatcher(None, re.sub(r'(?i)^The ',"", tv_show["title"]), re.sub(r'(?i)^The ',"", title)).ratio() * 100
				if matcher >= threshold_ratio: tv_show_list.append(tv_show)

			if tv_show_list: break

		if not tv_show_list: tv_show_list = show_list

		if (len(tv_show_list) == 0):
			log(__name__,"No TV Show found")
			return None
		elif (len(tv_show_list) == 1):
			log(__name__,"One TV Show found, autoselecting")
			tvshow_url = tv_show_list[0]['url']
		else:
			log(__name__,"More TV Shows found, user dialog for select")
			menu_dialog = []
			for tv_show in tv_show_list: menu_dialog.append(tv_show['title'])
			dialog = xbmcgui.Dialog()
			found_tv_show_id = dialog.select(self._t(32003), menu_dialog)
			if (found_tv_show_id == -1): return None # cancel dialog
			tvshow_url = tv_show_list[found_tv_show_id]['url']

		log(__name__,"Selected show URL: " + tvshow_url)
		return tvshow_url

	def search(self, item):
		title = item['mansearchstr'] if item['mansearch'] else item['tvshow']

		if item['3let_language'] and "cze" not in item['3let_language']:
			dialog = xbmcgui.Dialog()
			if dialog.yesno(self.addon.getAddonInfo('name'), self._t(32100), self._t(32101)):
				xbmc.executebuiltin("ActivateWindow(videossettings)")
			return results_with_stats(None, self.addon, title, item)

		all_tv_show_list = self.get_tv_show_list()
		if not all_tv_show_list: return results_with_stats(None, self.addon, title, item)

		tvshow_url = self.search_show_url(title, all_tv_show_list)
		if tvshow_url == None: return results_with_stats(None, self.addon, title, item)

		found_season_subtitles = self.search_season_subtitles(tvshow_url,item['season'])
		log(__name__, ["Season filter", found_season_subtitles])
		if found_season_subtitles == None: return results_with_stats(None, self.addon, title, item)

		episode_subtitle = self.filter_episode_from_season_subtitles(found_season_subtitles,item['season'],item['episode'])
		log(__name__, ["Episode filter", episode_subtitle])
		if episode_subtitle == None: return results_with_stats(None, self.addon, title, item)

		result_subtitles = [{
			'filename': HTMLParser.HTMLParser().unescape(episode_subtitle['full_title']),
			'link': self.server_url + episode_subtitle['link'],
			'lang': episode_subtitle['lang'],
			'rating': "0",
			'sync': False,
			'lang_flag': xbmc.convertLanguage(episode_subtitle['lang'],xbmc.ISO_639_1),
		}]

		log(__name__,["Search result", result_subtitles])

		return results_with_stats(result_subtitles, self.addon, title, item)

	def filter_episode_from_season_subtitles(self, season_subtitles, season, episode):
		for season_subtitle in season_subtitles:
			if (season_subtitle['episode'] == int(episode) and season_subtitle['season'] == int(season)):
				return season_subtitle
		return None

	def search_season_subtitles(self, show_url, show_series):
		res = urllib.urlopen(self.server_url + show_url)
		if not res.getcode() == 200: return None
		series_list_content = re.search("<section id=\"content\" class=\"grid-block\">(.+?)</section>", res.read(), re.IGNORECASE | re.DOTALL )
		if series_list_content == None: return None

		selected_serie_url = None
		series_list = []
		for series_list_html in re.findall("<div class=\"pd-subcategory\">(.+?)</div>", series_list_content.group(1).decode("utf-8"), re.IGNORECASE | re.DOTALL):
			serie_url, serie_number = re.search("<a href=\"(.+?)\">([\d]+?)\. .+?</a>", series_list_html, re.IGNORECASE).groups()
			if serie_number == show_series:
				selected_serie_url = serie_url
				break

		log(__name__, "Selected Serie URL: %s" % selected_serie_url)
		if selected_serie_url == None: return None

		res = urllib.urlopen(self.server_url + selected_serie_url)
		if not res.getcode() == 200: return None
		subtitles_list_content = re.search("<section id=\"content\" class=\"grid-block\">(.+?)</section>", res.read(), re.IGNORECASE | re.DOTALL )
		if subtitles_list_content == None: return None

		subtitles_list = []
		for subtitles_list_html in re.findall("<div class=\"pd-filebox\">(.+?)Detail</a></div></div>", subtitles_list_content.group(1).decode("utf-8"), re.IGNORECASE | re.DOTALL):
			subtitle = {}
			download_url, show_full_title = re.search("<div class=\"pd-float\"><a href=\"(.+?)\" >(.+?)</a></div>", subtitles_list_html, re.IGNORECASE | re.DOTALL).groups()
			show_title_with_numbers = re.search("(.+?) ([\d]+?)x([\d]+?)$",show_full_title).groups()
			# subtitle_version = re.search("Verze:&lt;\/div&gt;&lt;div class=\'pd-fl-m\'&gt;(.+?)&lt;\/div&gt;",subtitles_list_html, re.IGNORECASE | re.DOTALL | re.MULTILINE)
			# if subtitle_version: log("debug", subtitle_version.group(1))
			subtitle['full_title'] = show_full_title
			subtitle['season'] = int(show_title_with_numbers[1])
			subtitle['episode'] = int(show_title_with_numbers[2])
			subtitle['title'] = show_title_with_numbers[0]
			subtitle['lang'] = "Czech"
			subtitle['link'] = download_url
			subtitles_list.append(subtitle)

		return subtitles_list


