package com.baixador

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class BaixadorApp : Application() {

    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    @Volatile
    var ytdlpReady: Boolean = false
        private set

    @Volatile
    var ytdlpInitError: String? = null
        private set

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        initYoutubeDL()
    }

    private fun initYoutubeDL() {
        appScope.launch {
            try {
                YoutubeDL.getInstance().init(this@BaixadorApp)
                FFmpeg.getInstance().init(this@BaixadorApp)
                ytdlpReady = true
            } catch (e: YoutubeDLException) {
                ytdlpInitError = e.message ?: "Falha ao inicializar yt-dlp"
            } catch (e: Exception) {
                ytdlpInitError = e.message ?: "Erro desconhecido"
            }
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                getString(R.string.notification_channel_id),
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = getString(R.string.notification_channel_desc)
                setShowBadge(false)
            }
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(channel)
        }
    }
}
