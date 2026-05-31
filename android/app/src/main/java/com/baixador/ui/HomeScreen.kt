package com.baixador.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Error
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baixador.data.AudioQuality
import com.baixador.data.DownloadMode
import com.baixador.data.JobState
import com.baixador.data.JobStatus
import com.baixador.data.Quality
import com.baixador.ui.theme.BaixadorGreen
import com.baixador.ui.theme.ErrorRed
import com.baixador.ui.theme.WarnYellow
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun HomeScreen(vm: HomeViewModel) {
    val url by vm.url.collectAsStateWithLifecycle()
    val mode by vm.mode.collectAsStateWithLifecycle()
    val quality by vm.quality.collectAsStateWithLifecycle()
    val audioQuality by vm.audioQuality.collectAsStateWithLifecycle()
    val jobs by vm.jobs.collectAsStateWithLifecycle()
    val focusManager = LocalFocusManager.current

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
        ) {
            Header()
            Spacer(Modifier.height(16.dp))

            UrlInput(
                value = url,
                onValueChange = vm::setUrl,
                onSubmit = {
                    focusManager.clearFocus()
                    vm.startDownload()
                },
            )

            Spacer(Modifier.height(12.dp))
            ModeSelector(selected = mode, onSelect = vm::setMode)

            Spacer(Modifier.height(12.dp))
            when (mode) {
                DownloadMode.VIDEO -> QualityDropdown(
                    selected = quality,
                    options = Quality.values().toList(),
                    label = "Qualidade",
                    onSelect = vm::setQuality,
                    toLabel = { it.label },
                )
                DownloadMode.AUDIO -> QualityDropdown(
                    selected = audioQuality,
                    options = AudioQuality.values().toList(),
                    label = "Qualidade do áudio",
                    onSelect = vm::setAudioQuality,
                    toLabel = { it.label },
                )
                DownloadMode.PHOTO -> Spacer(Modifier.height(0.dp))
            }

            Spacer(Modifier.height(16.dp))
            DownloadButton(
                enabled = url.isNotBlank() && vm.ytdlpReady,
                onClick = {
                    focusManager.clearFocus()
                    vm.startDownload()
                },
            )

            if (!vm.ytdlpReady && vm.ytdlpError != null) {
                Spacer(Modifier.height(12.dp))
                ErrorBanner("Falha ao inicializar yt-dlp: ${vm.ytdlpError}")
            } else if (!vm.ytdlpReady) {
                Spacer(Modifier.height(12.dp))
                InfoBanner("Inicializando yt-dlp… isso pode levar alguns segundos na primeira vez.")
            }

            Spacer(Modifier.height(24.dp))
            Text(
                "Atividade",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            JobsList(jobs = jobs, onCancel = vm::cancel)
        }
    }
}

@Composable
private fun Header() {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(40.dp)
                .clip(CircleShape)
                .background(BaixadorGreen),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = Icons.Filled.Download,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(22.dp),
            )
        }
        Spacer(Modifier.width(10.dp))
        Column {
            Text("Baixador", style = MaterialTheme.typography.headlineSmall)
            Text(
                "Cole o link, escolha o formato, e baixe.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun UrlInput(value: String, onValueChange: (String) -> Unit, onSubmit: () -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        placeholder = {
            Text(
                "https://www.youtube.com/watch?v=…",
                fontFamily = FontFamily.Monospace,
                fontSize = 13.sp,
            )
        },
        modifier = Modifier.fillMaxWidth().heightIn(min = 80.dp),
        textStyle = MaterialTheme.typography.bodyLarge.copy(fontFamily = FontFamily.Monospace, fontSize = 14.sp),
        keyboardOptions = KeyboardOptions(
            capitalization = KeyboardCapitalization.None,
            autoCorrect = false,
            imeAction = ImeAction.Done,
        ),
        singleLine = false,
        maxLines = 4,
        shape = RoundedCornerShape(10.dp),
    )
}

@Composable
private fun ModeSelector(selected: DownloadMode, onSelect: (DownloadMode) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DownloadMode.values().forEach { mode ->
            val isSelected = mode == selected
            Box(
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(10.dp))
                    .background(
                        if (isSelected) BaixadorGreen else MaterialTheme.colorScheme.surface
                    )
                    .border(
                        2.dp,
                        if (isSelected) BaixadorGreen else MaterialTheme.colorScheme.surfaceVariant,
                        RoundedCornerShape(10.dp),
                    )
                    .clickable { onSelect(mode) }
                    .padding(vertical = 14.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    "${mode.emoji} ${mode.label}",
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 13.sp,
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun <T> QualityDropdown(
    selected: T,
    options: List<T>,
    label: String,
    onSelect: (T) -> Unit,
    toLabel: (T) -> String,
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = it },
    ) {
        OutlinedTextField(
            value = toLabel(selected),
            onValueChange = {},
            readOnly = true,
            label = { Text(label) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier
                .menuAnchor()
                .fillMaxWidth(),
            shape = RoundedCornerShape(10.dp),
        )
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier.background(MaterialTheme.colorScheme.surface),
        ) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(toLabel(option)) },
                    onClick = {
                        onSelect(option)
                        expanded = false
                    },
                )
            }
        }
    }
}

@Composable
private fun DownloadButton(enabled: Boolean, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier.fillMaxWidth().height(56.dp),
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = BaixadorGreen,
            disabledContainerColor = MaterialTheme.colorScheme.surface,
        ),
    ) {
        Icon(Icons.Filled.Download, contentDescription = null)
        Spacer(Modifier.width(8.dp))
        Text("Baixar", fontWeight = FontWeight.Bold, fontSize = 17.sp)
    }
}

@Composable
private fun JobsList(jobs: List<JobStatus>, onCancel: (String) -> Unit) {
    if (jobs.isEmpty()) {
        Text(
            "Nenhum download ainda. Cole um link acima.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(vertical = 8.dp),
        )
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        jobs.forEach { status ->
            JobCard(status = status, onCancel = onCancel)
        }
    }
}

@Composable
private fun JobCard(status: JobStatus, onCancel: (String) -> Unit) {
    val state = status.state
    val borderColor = when (state) {
        is JobState.Done -> BaixadorGreen
        is JobState.Failed -> ErrorRed
        is JobState.Cancelled -> ErrorRed
        is JobState.Running -> BaixadorGreen
        else -> MaterialTheme.colorScheme.surfaceVariant
    }

    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(10.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, borderColor),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StateIcon(state)
                Spacer(Modifier.width(8.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        status.job.url.take(80),
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        maxLines = 2,
                    )
                    Text(
                        "${status.job.mode.label} · ${formatTime(status.job.createdAt)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (state is JobState.Running || state is JobState.Queued) {
                    TextButton(onClick = { onCancel(status.job.id) }) {
                        Text("Cancelar", color = ErrorRed)
                    }
                }
            }
            if (state is JobState.Running) {
                Spacer(Modifier.height(8.dp))
                val pct = state.percent / 100f
                LinearProgressIndicator(
                    progress = { if (pct <= 0f) 0.02f else pct },
                    color = BaixadorGreen,
                    trackColor = MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)),
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    "%.0f%% · %s".format(state.percent, state.line.take(80)),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (state is JobState.Failed) {
                Spacer(Modifier.height(4.dp))
                Text(state.message.take(200), color = ErrorRed, style = MaterialTheme.typography.bodySmall)
            }
            if (state is JobState.Done) {
                Spacer(Modifier.height(4.dp))
                Text(
                    "Salvo em Downloads/Baixador (${state.savedFiles.size} arquivo${if (state.savedFiles.size == 1) "" else "s"})",
                    style = MaterialTheme.typography.bodySmall,
                    color = BaixadorGreen,
                )
            }
        }
    }
}

@Composable
private fun StateIcon(state: JobState) {
    when (state) {
        is JobState.Done -> Icon(Icons.Filled.CheckCircle, null, tint = BaixadorGreen)
        is JobState.Failed -> Icon(Icons.Filled.Error, null, tint = ErrorRed)
        is JobState.Cancelled -> Icon(Icons.Filled.Cancel, null, tint = ErrorRed)
        else -> Icon(Icons.Filled.Download, null, tint = WarnYellow)
    }
}

@Composable
private fun InfoBanner(text: String) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(10.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, WarnYellow),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(text, modifier = Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall, color = WarnYellow)
    }
}

@Composable
private fun ErrorBanner(text: String) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(10.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, ErrorRed),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(text, modifier = Modifier.padding(12.dp), style = MaterialTheme.typography.bodySmall, color = ErrorRed)
    }
}

private fun formatTime(ts: Long): String {
    val fmt = SimpleDateFormat("HH:mm", Locale.getDefault())
    return fmt.format(Date(ts))
}
