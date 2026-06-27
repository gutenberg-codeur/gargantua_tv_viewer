# Translation system for Gargantua
# Supports: English, French, German, Spanish

TRANSLATIONS = {
    "en": {
        # Buttons and UI elements
        "Recording": "Recording",
        "Day -1": "Day -1",
        "Today": "Today",
        "Day +1": "Day +1",
        "← -3 h": "← -3 h",
        "Now": "Now",
        "+ 3 h →": "+ 3 h →",
        "Recording (select a program)": "Recording (select a program)",

        # Error messages
        "VDR Error": "VDR Error",
        "mpv Error": "mpv Error",
        "EPG Error": "EPG Error",
        "SSH Error": "SSH Error",
        "Loading EPG...": "Loading EPG...",
        "Recording scheduled": "Recording scheduled",
        "Recording cancelled": "Recording cancelled",
        "Invalid dates for this event:\n": "Invalid dates for this event:\n",
        "Unknown VDR ChannelID for this event.": "Unknown VDR ChannelID for this event.",
        "Unable to send command to VDR:\n": "Unable to send command to VDR:\n",
        "Invalid dates:\n": "Invalid dates:\n",

        # Date/time labels
        "Day": "Day",
        "Time": "Time",
        "Today": "Today",
        "Yesterday": "Yesterday",
        "Tomorrow": "Tomorrow",
        "Day after tomorrow": "Day after tomorrow",

        # Messages
        "Waiting...": "Waiting...",
        "Congratulations! Grid completed!": "Congratulations! Grid completed!",
    },

    "fr": {
        # Boutons et éléments UI
        "Recording": "Enregistrement",
        "Day -1": "Jour -1",
        "Today": "Aujourd'hui",
        "Day +1": "Jour +1",
        "← -3 h": "⟵ -3 h",
        "Now": "Maintenant",
        "+ 3 h →": "+3 h ⟶",
        "Recording (select a program)": "Enregistrement (sélectionner une émission)",

        # Messages d'erreur
        "VDR Error": "Erreur VDR",
        "mpv Error": "Erreur mpv",
        "EPG Error": "Erreur EPG",
        "SSH Error": "Erreur SSH",
        "Loading EPG...": "Chargement EPG...",
        "Recording scheduled": "Enregistrement programmé",
        "Recording cancelled": "Enregistrement annulé",
        "Invalid dates for this event:\n": "Dates invalides pour cet évènement :\n",
        "Unknown VDR ChannelID for this event.": "ChannelID VDR inconnu pour cet évènement.",
        "Unable to send command to VDR:\n": "Impossible d'envoyer la commande à VDR :\n",
        "Invalid dates:\n": "Dates invalides :\n",

        # Libellés date/heure
        "Day": "Jour",
        "Time": "Heure",
        "Today": "Aujourd'hui",
        "Yesterday": "Hier",
        "Tomorrow": "Demain",
        "Day after tomorrow": "Après-demain",

        # Messages
        "Waiting...": "En attente...",
        "Congratulations! Grid completed!": "Bravo ! La grille est complétée !",
    },

    "de": {
        # Buttons und UI-Elemente
        "Recording": "Aufnahme",
        "Day -1": "Tag -1",
        "Today": "Heute",
        "Day +1": "Tag +1",
        "← -3 h": "← -3 h",
        "Now": "Jetzt",
        "+ 3 h →": "+ 3 h →",
        "Recording (select a program)": "Aufnahme (Programm auswählen)",

        # Fehlermeldungen
        "VDR Error": "VDR-Fehler",
        "mpv Error": "mpv-Fehler",
        "EPG Error": "EPG-Fehler",
        "SSH Error": "SSH-Fehler",
        "Loading EPG...": "EPG wird geladen...",
        "Recording scheduled": "Aufnahme geplant",
        "Recording cancelled": "Aufnahme abgebrochen",
        "Invalid dates for this event:\n": "Ungültige Daten für dieses Ereignis:\n",
        "Unknown VDR ChannelID for this event.": "Unbekannte VDR-ChannelID für dieses Ereignis.",
        "Unable to send command to VDR:\n": "Befehl kann nicht an VDR gesendet werden:\n",
        "Invalid dates:\n": "Ungültige Daten:\n",

        # Datums-/Uhrzeitbezeichnungen
        "Day": "Tag",
        "Time": "Zeit",
        "Today": "Heute",
        "Yesterday": "Gestern",
        "Tomorrow": "Morgen",
        "Day after tomorrow": "Übermorgen",

        # Meldungen
        "Waiting...": "Warten...",
        "Congratulations! Grid completed!": "Glückwunsch! Gitter abgeschlossen!",
    },

    "es": {
        # Botones y elementos de interfaz
        "Recording": "Grabación",
        "Day -1": "Día -1",
        "Today": "Hoy",
        "Day +1": "Día +1",
        "← -3 h": "← -3 h",
        "Now": "Ahora",
        "+ 3 h →": "+ 3 h →",
        "Recording (select a program)": "Grabación (seleccionar un programa)",

        # Mensajes de error
        "VDR Error": "Error de VDR",
        "mpv Error": "Error de mpv",
        "EPG Error": "Error de EPG",
        "SSH Error": "Error de SSH",
        "Loading EPG...": "Cargando EPG...",
        "Recording scheduled": "Grabación programada",
        "Recording cancelled": "Grabación cancelada",
        "Invalid dates for this event:\n": "Fechas inválidas para este evento:\n",
        "Unknown VDR ChannelID for this event.": "ChannelID de VDR desconocido para este evento.",
        "Unable to send command to VDR:\n": "No se puede enviar el comando a VDR:\n",
        "Invalid dates:\n": "Fechas inválidas:\n",

        # Etiquetas de fecha/hora
        "Day": "Día",
        "Time": "Hora",
        "Today": "Hoy",
        "Yesterday": "Ayer",
        "Tomorrow": "Mañana",
        "Day after tomorrow": "Pasado mañana",

        # Mensajes
        "Waiting...": "Esperando...",
        "Congratulations! Grid completed!": "¡Felicidades! ¡Cuadrícula completada!",
    }
}

def get_translator(language: str):
    """Get a translation function for the specified language."""
    lang = language.lower()
    if lang not in TRANSLATIONS:
        lang = "en"

    trans_dict = TRANSLATIONS[lang]

    def t(key: str) -> str:
        """Translate a key to the selected language."""
        return trans_dict.get(key, key)

    return t
