# Chaquopy Python
-keep class com.chaquo.python.** { *; }
-dontwarn com.chaquo.python.**

# FastAPI / uvicorn (called via Python, keep JNI paths)
-keep class org.python.** { *; }
-dontwarn org.python.**

# WebView JavaScript interface
-keepclassmembers class com.musicdl.MainActivity$Callback {
    *;
}

# MediaPlayer — keep error/complete listeners
-keepclassmembers class com.musicdl.MainActivity {
    android.media.MediaPlayer mediaPlayer;
}

# Keep app entry point
-keep class com.musicdl.MainActivity { *; }
