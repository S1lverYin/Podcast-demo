on run
	set launcherPath to "/Users/silver/Documents/computer science/voicescribe-webui/scripts/start-voicescribe.sh"
	do shell script quoted form of launcherPath
	display notification "VoiceScribe WebUI is ready." with title "VoiceScribe WebUI"
end run
