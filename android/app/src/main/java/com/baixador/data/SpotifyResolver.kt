package com.baixador.data

import android.util.Base64
import com.baixador.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Resolve um link do Spotify (track/album/playlist) para uma lista de queries
 * `ytsearch1:Artista Música` que o yt-dlp consegue baixar do YouTube Music.
 *
 * Usa Client Credentials Flow — não precisa de login do usuário, só credenciais
 * de app criadas em developer.spotify.com (gratuitas).
 */
class SpotifyResolver {

    data class Track(val artist: String, val title: String) {
        val ytdlpQuery: String get() = "ytsearch1:${artist.trim()} ${title.trim()}"
    }

    class NotConfiguredException : Exception("Credenciais do Spotify não configuradas")

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    @Volatile private var cachedToken: String? = null
    @Volatile private var tokenExpiresAt: Long = 0

    /** Identifica se a URL é do Spotify. */
    fun isSpotifyUrl(url: String): Boolean =
        url.contains("spotify.com/") || url.startsWith("spotify:")

    /** Extrai tipo (track/album/playlist) e id da URL. */
    private fun parseUrl(url: String): Pair<String, String>? {
        val regex = Regex("""(?:open\.spotify\.com/(?:intl-[a-z]+/)?|spotify:)(track|album|playlist|episode|show)[/:]([a-zA-Z0-9]+)""")
        val m = regex.find(url) ?: return null
        return m.groupValues[1] to m.groupValues[2]
    }

    suspend fun resolve(url: String): List<Track> = withContext(Dispatchers.IO) {
        val clientId = BuildConfig.SPOTIFY_CLIENT_ID
        val clientSecret = BuildConfig.SPOTIFY_CLIENT_SECRET
        if (clientId.isBlank() || clientSecret.isBlank()) throw NotConfiguredException()

        val (kind, id) = parseUrl(url) ?: throw IllegalArgumentException("URL Spotify inválida: $url")
        val token = obtainToken(clientId, clientSecret)

        when (kind) {
            "track" -> listOf(fetchTrack(token, id))
            "album" -> fetchAlbumTracks(token, id)
            "playlist" -> fetchPlaylistTracks(token, id)
            else -> throw UnsupportedOperationException("Tipo '$kind' não suportado")
        }
    }

    private fun obtainToken(clientId: String, clientSecret: String): String {
        cachedToken?.let { if (System.currentTimeMillis() < tokenExpiresAt) return it }

        val basic = Base64.encodeToString("$clientId:$clientSecret".toByteArray(), Base64.NO_WRAP)
        val req = Request.Builder()
            .url("https://accounts.spotify.com/api/token")
            .addHeader("Authorization", "Basic $basic")
            .post(FormBody.Builder().add("grant_type", "client_credentials").build())
            .build()

        http.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("Spotify auth falhou (${resp.code}): $body")
            val json = JSONObject(body)
            val token = json.getString("access_token")
            val expiresIn = json.optLong("expires_in", 3600)
            cachedToken = token
            tokenExpiresAt = System.currentTimeMillis() + (expiresIn - 60) * 1000
            return token
        }
    }

    private fun fetchTrack(token: String, id: String): Track {
        val json = api(token, "https://api.spotify.com/v1/tracks/$id")
        return trackFromJson(json)
    }

    private fun fetchAlbumTracks(token: String, id: String): List<Track> {
        val album = api(token, "https://api.spotify.com/v1/albums/$id")
        val albumArtist = album.getJSONArray("artists").getJSONObject(0).optString("name")
        val items = album.getJSONObject("tracks").getJSONArray("items")
        return List(items.length()) { i ->
            val t = items.getJSONObject(i)
            Track(
                artist = t.optJSONArray("artists")?.optJSONObject(0)?.optString("name").orEmpty().ifBlank { albumArtist },
                title = t.optString("name"),
            )
        }
    }

    private fun fetchPlaylistTracks(token: String, id: String): List<Track> {
        val out = mutableListOf<Track>()
        var url: String? = "https://api.spotify.com/v1/playlists/$id/tracks?limit=100"
        while (url != null) {
            val page = api(token, url)
            val items = page.getJSONArray("items")
            for (i in 0 until items.length()) {
                val t = items.getJSONObject(i).optJSONObject("track") ?: continue
                if (t.isNull("name")) continue
                out += trackFromJson(t)
            }
            url = if (page.isNull("next")) null else page.getString("next")
        }
        return out
    }

    private fun trackFromJson(t: JSONObject): Track {
        val artist = t.optJSONArray("artists")?.optJSONObject(0)?.optString("name").orEmpty()
        val title = t.optString("name")
        return Track(artist = artist, title = title)
    }

    private fun api(token: String, url: String): JSONObject {
        val req = Request.Builder().url(url).addHeader("Authorization", "Bearer $token").build()
        http.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) error("Spotify API ${resp.code}: $body")
            return JSONObject(body)
        }
    }
}
