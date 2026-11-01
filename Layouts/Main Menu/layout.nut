////////////////////////////////////////////////////////////////////////////////////////////////////////////
/* Main Menu Hyperspin v10.4
   __  ___     _        __  ___                __ __                           _    
  /  |/  /__ _(_)__    /  |/  /__ ___  __ __  / // /_ _____  ___ _______ ___  (_)__ 
 / /|_/ / _ `/ / _ \  / /|_/ / -_) _ \/ // / / _  / // / _ \/ -_) __(_-</ _ \/ / _ \
/_/  /_/\_,_/_/_//_/ /_/  /_/\__/_//_/\_,_/ /_//_/\_, / .__/\__/_/ /___/ .__/_/_//_/
                                                 /___/_/              /_/           
Design, Code and Art by Yaron


Wheel and Inertia modules by Oomek
Letters and 'System games count' code adapted from pcca theme */
////////////////////////////////////////////////////////////////////////////////////////////////////////////



local layout_t = clock()
local orderx = 0
local divider = "----"

class UserConfig {
	</ label=" ", help=" ", options=" ", order=orderx++ /> paramxx0=" "
	</ label="--- General ---", help=" ", options=" ", order=orderx++ /> paramxx1=" "
	</ label="Set perspective", help="'Full Screen' will stretch themes across the entire screen while '4x3' will show themes in their original Hyperspin aspect ratio.\n Users with '4x3' or '5x4' aspect ratio displays should set perspective to 'Full Screen'.",
		options="Full Screen,4x3", order=orderx++ />set_perspective="Full Screen"
	</ label="Enable screen bezel", help="Show screen bezel for 4x3 perspective when using wide screen displays (16x9, 16x10, 21x9)",
		options="No,Attractmode,Attractmode Framed,MAME,MAME Framed,MAME2,MAME Framed2,Cool Arcade,Real Arcade,Arcade Classics,Arcade Classics Framed,TV,TV Framed",
		order=orderx++ /> enable_bezel="Real Arcade"
	</ label="Force full bezels", help="Show bezels in full no matter what the screen resolution and aspect ratio is",
		options="Yes,No", order=orderx++ />force_bezels="No"
	</ label="Enable hyperspin extra animations", help="Joystick and Press-Start animations",
		options="Yes,No", order=orderx++ /> enable_hs_special="Yes"
	</ label="Animated joystick style", help="The graphical style of the hyperspin special animation joystick",
		options="Realistic,Cartoonish", order=orderx++ /> joystick_style="Cartoonish"
	</ label="Animated joystick color", help="The color of the hyperspin special animation joystick",
		options="Red,Green,Blue", order=orderx++ /> joystick_color="Red"

	</ label=" ", help=" ", options=" ", order=orderx++ /> paramxx2=" "
	</ label="--- Ambient sound and Music ---", help=" ", options=" ", order=orderx++ /> paramxx3=" "
	</ label="Enable ambient sound", help="Play ambient sound or music from the configured music folder",
		options="No,It's 1983,It's 1992,Music", order=orderx++ /> enable_ambience="No"
	</ label="Music folder",
		help="Path to the music folder, for example: C:\\downloads\\music \n If left empty, music will be played from the default music folder at: attract\\gtc-common\\music",
		options="", order=orderx++ /> music_path=""
	</ label="Music playing method", help="Loop current song, loop entire song list or shuffle (play random songs)",
		options="Loop List,Loop Song,Shuffle", order=orderx++ /> music_play_method="Shuffle"
	</ label="Previous song key", help="Choose the key to play previous song from the layout music folder",
		options="Custom1,Custom2,Custom3,Custom4,Custom5,Custom6", order=orderx++ /> user_prevsong_key="Custom4"
	</ label="Next song key", help="Choose the key to play next song from the layout music folder",
		options="Custom1,Custom2,Custom3,Custom4,Custom5,Custom6", order=orderx++ /> user_nextsong_key="Custom5"
	</ label="Show song title", help="Show the music title - will animate in and out from the top of the screen",
		options="Yes,No", order=orderx++ /> enable_song_title="Yes"
	</ label="Song title duration", help="The time in milliseconds that the song title will stay on the screen",
		options="1000,2000,3000,4000,5000,6000,7000,8000", order=orderx++ /> song_title_time="3000"
	</ label="Music delay", help="The time in milliseconds until music starts to play\n Accepts values between 0 and 300,000 (5 minutes)",
		options="", order=orderx++ /> set_music_delay="100"

	</ label=" ", help=" ", options=" ", order=orderx++ /> paramxx4=" "
	</ label="--- Wheel ---", help=" ", options=" ", order=orderx++ /> paramxx5=" "
	</ label="Type of wheel", help="Select round wheel or vertical wheel",
		options="Round,Vertical", order=orderx++ /> wheel_type="Round"
	</ label="Number of wheel slots", help="Number of slots in the wheel",
		options="5,7,9,11,13,15,17", order=orderx++ />wheel_slots="11"
	</ label="Wheel transition time", help="wheel spin time between game slots",
		options="100,200,300,600,1200", order=orderx++ /> transition_ms="200"
	</ label="Enable wheel entry animation", help="Animate the wheel into the screen when layout starts",
		options="Yes,No", order=orderx++ /> wheel_entry_anim="Yes"
	</ label="Enable wheel fadeout", help="Enable wheel fadeout",
		options="No,Partially,Completely", order=orderx++ /> wheel_fadeout="Completely"
	</ label="Wheel fade time", help="The time in milliseconds it takes to fade the wheel",
		options="500,1000,2000,3000", order=orderx++ /> wheel_fade_ms="500"
	</ label="Wheel fade delay time", help="The time in milliseconds until the wheel starts to fade",
		options="500,750,1000,1250,1500,1750,2000,2250,2500,2750,3000", order=orderx++ /> set_ms_delay="1000"
	</ label="Enable wheel pulse", help="Current wheel selection art will pulse once or in a loop",
		options="No,Once,Loop", order=orderx++ /> wheel_pulse="Once"
	</ label="Enable wheel background", help="Show wheel background texture",
		options="No,Light,Medium,Dark", order=orderx++ /> enable_wl_bg="No"
	</ label="Enable wheel sounds", help="Play sounds when navigating systems wheel",
		options="No,Random,Click,Arcade Joystick", order=orderx++ /> enable_nav_sound="Random"
	</ label="Additional wheel click sound", help="A click sound will be played in addition to Random sounds",
		options="Yes,No", order=orderx++ /> enable_additional_sound="Yes"
	</ label="Enable wheel pointer", help="Show animated wheel pointer",
		options="Yes,No", order=orderx++ /> enable_pointer="No"
	</ label="Enable letters",
		help="Show graphical letters on the screen when pressing the wheel's 'Next Letter' or 'Previous Letter' hotkeys set in the Controls menu.\n 'System Display Name' option will seek the letters in a folder identical to the current system display name (attract/letters/mame for example).",
		options="No,Default,White,By System Display Name,Hardcoded", order=orderx++ /> letters_type="Default"

	</ label=" ", help=" ", options=" ", order=orderx++ /> paramxx6=" "
	</ label="--- Menu Videos ---", help=" ", options=" ", order=orderx++ /> paramxx7=" "
	</ label="Enable video scanline or aperture effect", help="Show video scanline or aperture effect",
		options="No,Scanlines,Aperture", order=orderx++ /> enable_scanlines="No"
	</ label="Mute videos", help="Mute the sound of videos",
		options="Yes,No", order=orderx++ /> sound="No"

	</ label=" ", help=" ", options=" ", order=orderx++ /> paramxx8=" "
	</ label="--- System Info ---", help=" ", options=" ", order=orderx++ /> paramxx9=" "
	</ label="Show systems info", help="Show systems info",
		options="No,Name,Name And Games Count (One Line),Name And Games Count (Two Lines)", order=orderx++ /> enable_gameinfo="Name And Games Count (Two Lines)"
	</ label="Show systems count", help="Show the number of systems",
		options="Yes,No", order=orderx++ /> enable_sys_count="No"
	</ label="Enable random text colors", help="Enable system info random text colors",
		options="Fixed,Dynamic,No", order=orderx++ /> enable_colors="No"
}
my_config <- fe.get_config()


// modules
fe.load_module("wheel")
fe.load_module("inertia")
fe.load_module("animate")
fe.load_module("file")
fe.load_module("file-format")
fe.load_module("gtc")
fe.load_module("favorites")
fe.load_module("animated-joystick")


// Initializations

DEBUG_TIMERS <- true
DEBUG_FILES <- false

// aspect ratio and resolution
local aspect = fe.layout.width / fe.layout.height.tofloat()
local aspect_name = ""
switch( aspect.tostring() )
{
    case "2.4":
    case "2.37037":
        aspect_name = "21x9"
	break
    case "1.77865":  //for 1366x768 screen
    case "1.77778":  //for any other 16x9 resolution
        aspect_name = "16x9"
	break
    case "1.6":
        aspect_name = "16x10"
	break
    case "1.33333":
        aspect_name = "4x3"
	break
    case "1.25":
        aspect_name = "5x4"
	break
	default:
		aspect_name = "16x9"
	break
}
print("Attract-Mode Version: " + FeVersion + "\n" + "Screen aspect ratio: "+aspect_name+"\n" + "Resolution: "+ScreenWidth+"x"+ScreenHeight+"\n" + "Shader GLSL available: "+ShadersAvailable+"\n" + "OS: "+OS+"\n")


if( my_config["set_perspective"] == "4x3" )
{
	fe.layout.preserve_aspect_ratio = true

	if( my_config["force_bezels"] == "Yes" )
		fe.layout.width = fe.layout.width / 1.33333
	else
	{
		fe.layout.width = 1440
		fe.layout.height = 1080
	}
}
else
	fe.layout.preserve_aspect_ratio=false

flx <- fe.layout.width
fly <- fe.layout.height
flw <- fe.layout.width
flh <- fe.layout.height


// wheel fade timer
wheel_delay <- my_config["set_ms_delay"].tointeger()
wheel_play <- wheel_delay

// wheel and pointer speed
local wheel_speed = my_config["transition_ms"].tointeger()

// number of wheel slots
local wheel_slots = my_config["wheel_slots"].tointeger() + 2

// letters timers
local rtime = 0
local glob_time = 0
local glob_delay = wheel_delay
if( glob_delay > 1000 )
	glob_delay = 1000


// random number function
function random(minNum, maxNum)
{
	return floor(((rand() % 10000 ) / 10000.0) * (maxNum - (minNum - 1)) + minNum)
}



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Font

fe.layout.font = "SF Slapstick Comic Bold Oblique"



//////////////////////////////////////////////////////////////////////////////////////////////////
// Favorites

if( fe.nv.rawin( "GLOBAL_FAVORITES_LIST_LOADED" ) )
{
	if( fe.nv["GLOBAL_FAVORITES_LIST_LOADED"] == 0 )
	{
		test_romlist()
		get_favorites()
	}
}



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Snap

// black background when no snap is available
local snapbg = fe.add_image( FeConfigDirectory+"gtc-common/art/arcade/vertical_cover.png", 0, 0, flw, flh )

//create surface for snap
local surface_snap = fe.add_surface( fe.layout.width, fe.layout.height )
surface_snap.set_pos( 0, 0 )
local snap = surface_snap.add_artwork( "themes", 0, 0, surface_snap.width, surface_snap.height )
snap.trigger = Transition.EndNavigation
snap.preserve_aspect_ratio = false

// mute the video
if( my_config["sound"] == "Yes" )
	snap.video_flags = Vid.NoAudio

// dynamically show/hide bezels for settings, controls, credits and exit screens
local menu_bezels = fe.add_image( "images/menu_bezels.png", 0, 0, flw, flh )
menu_bezels.visible = false

local sys_main_menu
fe.add_transition_callback( "mainMenu_transitions" )
function mainMenu_transitions( ttype, var, ttime )
{
	switch( ttype )
	{
		case Transition.StartLayout:
		case Transition.ToNewList:
		case Transition.EndNavigation:
			if( my_config["set_perspective"] == "Full Screen" )
			{
				sys_main_menu = fe.game_info(Info.Title, var)

				if(	sys_main_menu == "Ingame Settings" || sys_main_menu == "Controls" || sys_main_menu == "Credits" || sys_main_menu == "Exit HyperSpin" )
					menu_bezels.visible = true
				else
					menu_bezels.visible = false
			}
		break
	}
	return false
}



////////////////////////////////////////////////////////////////////////////////////////////////////////
// System info

// Games count
local gc_x, gc_y, gc_x_b, gc_y_b
local target_color = 150
local speed_color = 160

local font_size = flh*0.042
if( fe.layout.preserve_aspect_ratio == true )
	font_size = flh*0.035

if( my_config["enable_hs_special"] == "No" )
{
	if( fe.layout.preserve_aspect_ratio == true )
	{
		gc_x_b = flx*0.039
		gc_x = flx*0.04
		gc_y_b = fly*0.904
		gc_y = fly*0.905
	}
	else
	{
		gc_x_b = flx*0.009
		gc_x = flx*0.01
		gc_y_b = fly*0.904
		gc_y = fly*0.905
	}
}

if( my_config["enable_hs_special"] == "Yes" )
{
	if( fe.layout.preserve_aspect_ratio == true )
	{
		gc_x_b = flx*0.07
		gc_x = flx*0.071
		gc_y_b = fly*0.829
		gc_y = fly*0.83
	}
	else
	{
		gc_x_b = flx*0.067
		gc_x = flx*0.068
		gc_y_b = fly*0.819
		gc_y = fly*0.82
	}
}

local m_infos_b = fe.add_text( "",gc_x_b, gc_y_b, flw*0.5, flh*0.1 )
local m_infos = fe.add_text( "",gc_x, gc_y, flw*0.5, flh*0.1 )

m_infos_b.align = Align.Left
m_infos_b.charsize = font_size
m_infos_b.set_rgb(0, 0, 0)

m_infos.align = Align.Left
m_infos.charsize = font_size
m_infos.set_rgb(255, 255, 0)


if( my_config["enable_gameinfo"] == "Name" || my_config["enable_gameinfo"] == "No" )
{
	m_infos_b.visible = false
	m_infos.visible = false
}


// Random colors for all text
local red, green, blue
brightrand <- function() {
	return 255-(rand()/255)
}

if( my_config["enable_colors"] == "Fixed" )
{
	// Color Transitions
	fe.add_transition_callback( "color_transitions_ini" )
	color_transitions_ini <- function( ttype, var, ttime ) {
		switch( ttype )
		{
			case Transition.StartLayout:
			case Transition.EndNavigation:
				red = brightrand()
				green = brightrand()
				blue = brightrand()
			break
		}
		return false
	}
}


// System name
if( my_config["enable_gameinfo"] != "No" )
{
	local title = ""
	local title_b = "" //black shadow
	local x_title, x_title_b, x_filter_b, x_filter, y_title, y_title_b


	if( my_config["enable_hs_special"] == "No" )
	{
		// System
		if( fe.layout.preserve_aspect_ratio == true )
		{
			x_title_b = flx*0.039
			x_title = flx*0.04
			y_title_b = fly*0.864
			y_title = fly*0.865
			if( my_config["enable_gameinfo"] == "Name" || my_config["enable_gameinfo"] == "Name And Games Count (One Line)" )
			{
				y_title_b = fly*0.904
				y_title = fly*0.905
			}

			title_b = fe.add_text("[Title]", x_title_b, y_title_b, flw*0.5, flh*0.1)
			title = fe.add_text("[Title]", x_title, y_title, flw*0.5, flh*0.1)
		}
		else  // full screen
		{
			x_title_b = flx*0.009
			x_title = flx*0.01
			y_title_b = fly*0.854
			y_title = fly*0.855
			if( my_config["enable_gameinfo"] == "Name" || my_config["enable_gameinfo"] == "Name And Games Count (One Line)" )
			{
				y_title_b = fly*0.904
				y_title = fly*0.905
			}
			title_b = fe.add_text("[Title]", x_title_b, y_title_b, flw*0.5, flh*0.1)
			title = fe.add_text("[Title]", x_title, y_title, flw*0.5, flh*0.1)
		}

		title_b.align = Align.Left
		title_b.charsize = font_size
		title_b.set_rgb(0, 0, 0)

		title.align = Align.Left
		title.charsize = font_size
		title.set_rgb(255, 255, 0)
	}

	if( my_config["enable_hs_special"] == "Yes" )
	{
		// System
		if( fe.layout.preserve_aspect_ratio == true )
		{
			x_title_b = flx*0.07
			x_title = flx*0.071
			y_title_b = fly*0.789
			y_title = fly*0.79
			if( my_config["enable_gameinfo"] == "Name" || my_config["enable_gameinfo"] == "Name And Games Count (One Line)" )
			{
				y_title_b = fly*0.819
				y_title = fly*0.82
			}
			title_b = fe.add_text("[Title]", x_title_b, y_title_b, flw*0.6, flh*0.1)
			title = fe.add_text("[Title]", x_title, y_title, flw*0.6, flh*0.1)
		}
		else  // full screen
		{
			x_title_b = flx*0.067
			x_title = flx*0.068
			y_title_b = fly*0.769
			y_title = fly*0.77
			if( my_config["enable_gameinfo"] == "Name" || my_config["enable_gameinfo"] == "Name And Games Count (One Line)" )
			{
				y_title_b = fly*0.819
				y_title = fly*0.82
			}
			title_b = fe.add_text("[Title]", x_title_b, y_title_b, flw*0.6, flh*0.1)
			title = fe.add_text("[Title]", x_title, y_title, flw*0.6, flh*0.1)
		}

		title_b.align = Align.Left
		title_b.charsize = font_size
		title_b.set_rgb(0, 0, 0)

		title.align = Align.Left
		title.charsize = font_size
		title.set_rgb(255, 255, 0)
	}


	// system name
	local start_transition_title = {when = Transition.StartLayout, property = "x", start = flx*-2, end = x_title, time = 1800}
	animation.add( PropertyAnimation( title, start_transition_title ) )

	local start_transition_title_b = {when = Transition.StartLayout, property = "x", start = flx*-2, end = x_title_b, time = 1800}
	animation.add( PropertyAnimation( title_b, start_transition_title_b ) )

	// games count
	local start_transition_gc = {when = Transition.StartLayout, property = "x", start = flx*-2, end = gc_x, time = 1800}
	animation.add( PropertyAnimation( m_infos, start_transition_gc ) )

	local start_transition_gc_b = {when = Transition.StartLayout, property = "x", start = flx*-2, end = gc_x_b, time = 1800}
	animation.add( PropertyAnimation( m_infos_b, start_transition_gc_b ) )

	title_text_transition <- function( ttype, var, ttime )
	{
		if( ttype == Transition.ToNewSelection )
		{
			start_transition_title.time = 1
			start_transition_title_b.time = 1
			start_transition_gc.time = 1
			start_transition_gc_b.time = 1
		}

		return false
	}
	fe.add_transition_callback( "title_text_transition" )

	// system name
	local move_transition_title = {when = Transition.ToNewSelection, property = "x", start = flx*-2, end = x_title, time = 1800}
	animation.add( PropertyAnimation( title, move_transition_title ) )

	local move_transition_title_b = {when = Transition.ToNewSelection, property = "x", start = flx*-2, end = x_title_b, time = 1800}
	animation.add( PropertyAnimation( title_b, move_transition_title_b ) )

	// games count
	local move_transition_gc = {when = Transition.ToNewSelection, property = "x", start = flx*-2, end = gc_x, time = 1800}
	animation.add( PropertyAnimation( m_infos, move_transition_gc ) )

	local move_transition_gc_b = {when = Transition.ToNewSelection, property = "x", start = flx*-2, end = gc_x_b, time = 1800}
	animation.add( PropertyAnimation( m_infos_b, move_transition_gc_b ) )


	// Count systems games
	main_infos <- {}
	if( !file_exist(FeConfigDirectory + "gtc.stats") )
	{
		fe.overlay.splash_message ("Counting games, please wait...")
		print("Main menu created the gtc.stats file!\n")
		refresh_stats()
	}
	main_infos <- LoadStats()

	local system_title = fe.add_text("[Title]", flx*3, 0, 0, 0)
	stats_text_update <- function( sys )
	{
		if( main_infos.rawin( sys ) )
		{
			if( my_config["enable_gameinfo"] == "Name" )
			{
				title.msg = system_title.msg
				title_b.msg = title.msg
			}
			if( my_config["enable_gameinfo"] == "Name And Games Count (One Line)" )
			{
				title.msg = system_title.msg + ", " + main_infos[sys].cnt + " Games"
				title_b.msg = title.msg
			}
			if( my_config["enable_gameinfo"] == "Name And Games Count (Two Lines)" )
			{
				title.msg = system_title.msg
				title_b.msg = title.msg
				m_infos.msg = main_infos[sys].cnt + " Games"
				m_infos_b.msg = main_infos[sys].cnt + " Games"
			}
		}
		else
		{
			title.msg = system_title.msg
			title_b.msg = title.msg
		}
	}

	main_menu_stats <- function( ttype, var, ttime )
	{
		if( ttype == Transition.EndNavigation || ttype == Transition.ToNewList )
		{
			local sys = fe.game_info(Info.Title, var)
			//print("sys = "+sys+"\n")

			if( sys != "Ingame Settings" && sys != "Controls" && sys != "Credits" && sys != "Exit HyperSpin" )
				stats_text_update( sys )
			else
			{
				title.msg = ""
				title_b.msg = ""
				m_infos.msg = ""
				m_infos_b.msg = ""
			}
		}

		return false
	}
	fe.add_transition_callback( "main_menu_stats" )

	// Random color for info text
	if( my_config["enable_colors"] == "Fixed" )
	{
		// Color Transitions
		fe.add_transition_callback( "color_transitions_title" )
		color_transitions_title <- function( ttype, var, ttime ) {
			switch( ttype )
			{
				case Transition.StartLayout:
				case Transition.EndNavigation:
					if( title != "" )
						title.set_rgb(red, green, blue)

					if( my_config["enable_gameinfo"] == "Name And Games Count (Two Lines)" )
							m_infos.set_rgb(red, green, blue)
				break
			}
			return false
		}
	}

	// must do this before adding inertia so base color will be white
	if( my_config["enable_colors"] == "Dynamic" )
	{
		title.set_rgb(255, 255, 255)
		if( my_config["enable_gameinfo"] == "Name And Games Count (Two Lines)" )
			m_infos.set_rgb(255, 255, 255)
	}

	title = Inertia( title, speed_color, "red", "green", "blue" )
	if( my_config["enable_gameinfo"] == "Name And Games Count (Two Lines)" )
		m_infos = Inertia( m_infos, speed_color, "red", "green", "blue" )

	if( my_config["enable_colors"] == "Dynamic" )
	{
		title.tween_red = Tween.FullSine
		title.tween_green = Tween.FullSine
		title.tween_blue = Tween.FullSine
		title.time_red = speed_color
		title.time_green = speed_color
		title.time_blue = speed_color
		title.loop_red = true
		title.to_red = target_color
		title.loop_blue = true
		title.to_blue = target_color
		title.loop_green = true
		title.to_green = target_color
		title.delay_green = -1 * (speed_color*0.33) // phase offset 33%
		title.delay_blue = -1 * (speed_color*0.66) // phase offset 66%

		if( my_config["enable_gameinfo"] == "Name And Games Count (Two Lines)" )
		{
			m_infos.tween_red = Tween.FullSine
			m_infos.tween_green = Tween.FullSine
			m_infos.tween_blue = Tween.FullSine
			m_infos.time_red = speed_color
			m_infos.time_green = speed_color
			m_infos.time_blue = speed_color
			m_infos.loop_red = true
			m_infos.to_red = target_color
			m_infos.loop_blue = true
			m_infos.to_blue = target_color
			m_infos.loop_green = true
			m_infos.to_green = target_color
			m_infos.delay_green = -1 * (speed_color*0.33) // phase offset 33%
			m_infos.delay_blue = -1 * (speed_color*0.66) // phase offset 66%
		}
	}
}


// Systems count
if( my_config["enable_sys_count"] == "Yes" )
{
	local filter = ""
	local filter_b = "" //black shadow
	local x_filter_b, x_filter


	if( my_config["enable_hs_special"] == "No" )
	{
		if( fe.layout.preserve_aspect_ratio == true )
		{
			x_filter_b = flx*0.567
			x_filter = flx*0.568

			filter_b = fe.add_text( "System: [ListEntry]/[ListSize]", x_filter_b, fly*0.902, flw*0.4, flh*0.1 )
			filter = fe.add_text( "System: [ListEntry]/[ListSize]", x_filter, fly*0.903, flw*0.4, flh*0.1 )
		}
		else
		{
			x_filter_b = flx*0.588
			x_filter = flx*0.589

			filter_b = fe.add_text( "System: [ListEntry]/[ListSize]", x_filter_b, fly*0.904, flw*0.4, flh*0.1 )
			filter = fe.add_text( "System: [ListEntry]/[ListSize]", x_filter, fly*0.905, flw*0.4, flh*0.1 )
		}

		filter_b.align = Align.Right
		filter_b.charsize = font_size
		filter_b.set_rgb(0, 0, 0)

		filter.align = Align.Right
		filter.charsize = font_size
		filter.set_rgb(255, 255, 0)
	}

	if( my_config["enable_hs_special"] == "Yes" )
	{
		if( fe.layout.preserve_aspect_ratio == true )
		{
			// Current System out of total number of Systems
			x_filter_b = flx*0.529
			x_filter = flx*0.53

			filter_b = fe.add_text( "System: [ListEntry]/[ListSize]", x_filter_b, fly*0.829, flw*0.4, flh*0.1 )
			filter = fe.add_text( "System: [ListEntry]/[ListSize]", x_filter, fly*0.83, flw*0.4, flh*0.1 )
		}
		else
		{
			x_filter_b = flx*0.529
			x_filter = flx*0.53

			filter_b = fe.add_text( "System: [ListEntry]/[ListSize]", x_filter_b, fly*0.819, flw*0.4, flh*0.1 )
			filter = fe.add_text( "System: [ListEntry]/[ListSize]", x_filter, fly*0.82, flw*0.4, flh*0.1 )
		}

		filter_b.align = Align.Right
		filter_b.charsize = font_size
		filter_b.set_rgb(0, 0, 0)

		filter.align = Align.Right
		filter.charsize = font_size
		filter.set_rgb(255, 255, 0)
	}

	filter_b.zorder = 20
	filter.zorder = 21

	// Random color for info text
	if( my_config["enable_colors"] == "Fixed" )
	{
		brightrand <- function() {
			return 255-(rand()/255)
		}

		// Color Transitions
		fe.add_transition_callback( "color_transitions_sys" )
		color_transitions_sys <- function( ttype, var, ttime ) {
			switch( ttype )
			{
				case Transition.StartLayout:
				case Transition.EndNavigation:
				if( filter != "" )
					filter.set_rgb(red,green,blue)
				break
			}
			return false
		}
	}

	// must do this before adding inertia so base color will be white
	if( my_config["enable_colors"] == "Dynamic" )
		filter.set_rgb(255, 255, 255)

	filter = Inertia( filter, speed_color, "red", "green", "blue" )

	if( my_config["enable_colors"] == "Dynamic" )
	{
		filter.tween_red = Tween.FullSine
		filter.tween_green = Tween.FullSine
		filter.tween_blue = Tween.FullSine
		filter.time_red = speed_color
		filter.time_green = speed_color
		filter.time_blue = speed_color
		filter.loop_red = true
		filter.to_red = target_color
		filter.loop_blue = true
		filter.to_blue = target_color
		filter.loop_green = true
		filter.to_green = target_color
		filter.delay_green = -1 * (speed_color*0.33) // phase offset 33%
		filter.delay_blue = -1 * (speed_color*0.66) // phase offset 66%
	}

	local start_transition_filter = {when = Transition.StartLayout, property = "x", start = flx*2, end = x_filter, time = 1800}
	animation.add( PropertyAnimation( filter, start_transition_filter ) )

	local start_transition_filter_b = {when = Transition.StartLayout, property = "x", start = flx*2, end = x_filter_b, time = 1800}
	animation.add( PropertyAnimation( filter_b, start_transition_filter_b ) )

	sys_text_transition <- function( ttype, var, ttime )
	{
		if( ttype == Transition.ToNewSelection )
		{
			start_transition_filter.time = 1
			start_transition_filter_b.time = 1
		}

		if( ttype == Transition.EndNavigation || ttype == Transition.ToNewList )
		{
			local sys = fe.game_info(Info.Title, var)
			if( sys == "Ingame Settings" || sys == "Controls" || sys == "Credits" || sys == "Exit HyperSpin" )
			{
				filter.msg = ""
				filter_b.msg = ""
			}
			else
			{
				filter.msg = "System: [ListEntry]/[ListSize]"
				filter_b.msg = "System: [ListEntry]/[ListSize]"
			}
		}

		return false
	}
	fe.add_transition_callback( "sys_text_transition" )

	local move_transition_filter = {when = Transition.ToNewSelection, property = "x", start = flx*2, end = x_filter, time = 1800}
	animation.add( PropertyAnimation( filter, move_transition_filter ) )

	local move_transition_filter_b = {when = Transition.ToNewSelection, property = "x", start = flx*2, end = x_filter_b, time = 1800}
	animation.add( PropertyAnimation( filter_b, move_transition_filter_b ) )
}



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Wheel background

local wheel_bg
local wheel_bg_alpha = 0

if( my_config["enable_wl_bg"] != "No" )
{
	local x = flw*0.74
	if( layout_config["set_perspective"] == "4x3" )
		x = flw*0.725

	if( layout_config["wheel_type"] == "Round" )
		wheel_bg = fe.add_image( "wheel_art.png", x, 0, flw*0.36, flh )
	else
		wheel_bg = fe.add_image( "wheel_vert.png", x, 0, flw*0.22, flh )

	wheel_bg.zorder = 19
	wheel_bg.mipmap = true

	if( layout_config["enable_wl_bg"] == "Light" )
		wheel_bg_alpha = 80
	else if( layout_config["enable_wl_bg"] == "Medium" )
		wheel_bg_alpha = 160
	else if( layout_config["enable_wl_bg"] == "Dark" )
		wheel_bg_alpha = 255

	wheel_bg.alpha = wheel_bg_alpha

	if( layout_config["wheel_entry_anim"] == "Yes" )
	{
		wheel_bg = Inertia( wheel_bg, 700, "x", "y" )
		wheel_bg.x = flw*1.5
		wheel_bg.to_x = x
	}
}



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Pointer

if( my_config["enable_pointer"] == "Yes" )
{
	local start_x = 0.91

	pointer <- fe.add_image("pointers/default.png", flw*1.75, fly*0.325, flw*0.2, flh*0.35)
	pointer.preserve_aspect_ratio = true

	// for best results keep inertia value same as wheel speed
	pointer = Inertia(pointer, 700, "x", "y")

	if( my_config["wheel_entry_anim"] == "No" )
		pointer.time_x = 1

	// force aspect ratio on the pointer by moving it once (seems to be an AM bug)
	pointer.to_x = flw * start_x

	update_speed <- true

	fe.add_transition_callback( "transition_pointer" )
	transition_pointer <- function( ttype, var, ttime )
	{
		switch ( ttype )
		{
			case Transition.ToNewSelection:
				if( update_speed )
				{
					pointer.time_x = wheel_speed
					update_speed = false
				}
				pointer.to_x = flx*0.889
			break
			case Transition.EndNavigation:
				pointer.to_x = flx*start_x
			break
		}
		return false
	}
}



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Wheel

// define wheel configuration
local wheel_config =
{
    function init()
    {
        // Wheel global parameters
 		if( my_config["set_perspective"] == "4x3" )
		{
			x <- flw * 0.835
			if( aspect_name == "16x10" )
				x <- flw * 0.83
			if( aspect_name == "5x4" )
				x <- flw * 0.78
		}
		else
		{
			x <- flw * 0.85
			if( aspect_name == "16x10" )
				x <- flw * 0.83
			if( aspect_name == "4x3" )
				x <- flw * 0.8
			if( aspect_name == "5x4" )
				x <- flw * 0.78
		}

        y <- flh * 0.5
        width <- flw
        height <- flh
        slots <- wheel_slots
        speed <- wheel_speed

        artwork_label <- "wheel"
        video_flags <- Vid.ImagesOnly
		preserve_aspect_ratio <- true

        zorder <- 1
        trigger <- Transition.ToNewSelection

        preset <- "arch-vertical"

        // Arch preset parameters
		if( my_config["wheel_type"] == "Round" )
			arch <- 80.0
		else
			arch <- 0.0

        // Dynamic table override defines to be updated in update()
        layout.width <- []
        layout.height <- []
    }

    function update()
    {
        for( local i = 0; i < slots; i++ )
        {
			if( my_config["set_perspective"] == "4x3" )
			{
				layout.width[i] = flh * 0.29
				layout.height[i] = flh * 0.29 / 2.5
			}
			else
			{
				layout.width[i] = flh * 0.32
				layout.height[i] = flh * 0.32 / 2.5
			}
        }

		// current slot
		if( my_config["set_perspective"] == "4x3" )
		{
			layout.width[slots/2] = flh * 0.38
			layout.height[slots/2] = flh * 0.38 / 2.5
		}
		else
		{
			layout.width[slots/2] = flh * 0.5
			layout.height[slots/2] = flh * 0.5 / 2.5
		}
    }
}

// create wheel
local wheel = fe.add_wheel( wheel_config )


// animate wheel
if( my_config["wheel_entry_anim"] == "Yes" )
{
	local wheel_x_preset = wheel.x
	wheel.x = flw * 1.5
	wheel = Inertia( wheel, 700, "x", "y" )
	wheel.to_x = wheel_x_preset

	// don't allow wheel navigation until it enters the screen
	allow_navigation <- false

	fe.add_ticks_callback( "ticks_wait_for_wheel" )
	ticks_wait_for_wheel <- function( ttime )
	{
		if( wheel.x < flw )
			allow_navigation = true
	}

	fe.add_signal_handler( "signal_wait_for_wheel" )
	signal_wait_for_wheel <- function(str)
	{
		switch( str )
		{
			case "up":
			case "down":
				if( !allow_navigation )
					return true
			break
		}
		return false
	}
}


// Wheel fading code starts here
local _alpha, _partially = 30

if( my_config["wheel_fadeout"] != "No" )
{
	first_tick <- 0
	stop_fading <- true
	wheel_fade_ms <- 0
	try { wheel_fade_ms = my_config["wheel_fade_ms"].tointeger() } catch ( e ) { wheel_fade_ms = 500 }

	if( wheel_fade_ms > 0 )
	{
		fe.add_transition_callback( "transition_wheel_fade" )
		transition_wheel_fade <- function( ttype, var, ttime )
		{
			if( ttype == Transition.ToNewSelection || ttype == Transition.ToNewList )
			{
				first_tick = -1
				wheel_delay = fe.layout.time
				if( my_config["enable_pointer"] != "No")
					pointer.alpha = 255
				if( my_config["enable_wl_bg"] != "No" )
					wheel_bg.alpha = wheel_bg_alpha
			}
			return false
		}

		fe.add_ticks_callback( "ticks_wheel_alpha" )
		ticks_wheel_alpha <- function( ttime )
		{
			local _elpased = 0
			if( first_tick == -1 )
				stop_fading = false


			// handle wheel alpha after keyboard search
			if( first_tick > 0 )
				_elpased = ttime - first_tick

			if( _elpased < wheel_fade_ms )
				wheel.alpha = 255


			// Wheel fading
			if( !stop_fading && ttime - wheel_delay >= wheel_play )
			{
				local elapsed = 0

				if( first_tick > 0 )
					elapsed = ttime - first_tick

				if( elapsed > wheel_fade_ms )
				{
					if( my_config["wheel_fadeout"] == "Partially" )
						wheel.alpha = _partially
					else
						wheel.alpha = 0
				}
				else
				{
					_alpha = (255 * (wheel_fade_ms - elapsed)) / wheel_fade_ms
					if( _alpha < _partially && my_config["wheel_fadeout"] == "Partially" )
						_alpha = _partially

					wheel.alpha = _alpha

					if( my_config["enable_pointer"] != "No" )
						pointer.alpha = _alpha

					if( my_config["enable_wl_bg"] != "No" )
					{
						_alpha = (wheel_bg_alpha * (wheel_fade_ms - elapsed)) / wheel_fade_ms
						if( _alpha < _partially && my_config["wheel_fadeout"] == "Partially" )
							_alpha = _partially
						wheel_bg.alpha = _alpha
					}
				}

				if( elapsed > wheel_fade_ms )
				{
					//So we don't keep doing the loop above when all values have 0 alpha
					stop_fading = true
				}

				if( first_tick == -1 )
					first_tick = ttime
			}
		}
	}
}

// Pulse current wheel logo
if( my_config["wheel_pulse"] != "No" )
{
	local pulse_once = false

	local pulse_slot = fe.add_clone( wheel.sel_slot )
	pulse_slot.zorder = wheel.cfg.zorder + wheel.selected_slot_idx - 2

	local pulse = 0.0
	local pulse_freq = 0.33 // times per second
	local pulse_scale = 0.3

	 // no need for animation, just drop it in tick
	update_pulse <- function()
	{
		if( pulse_once )
			return

		if( !wheel.velocity.running )
			pulse += pulse_freq / ScreenRefreshRate
		else
			pulse = 0.0

		if( pulse > 1.0 ) pulse = 0.0

		local sel = wheel.sel_slot
		pulse_slot.x = sel.x
		pulse_slot.y = sel.y
		pulse_slot.width = sel.width * ( 1.0 + pulse * pulse_scale )
		pulse_slot.height = sel.height * ( 1.0 + pulse * pulse_scale )
		pulse_slot.rotation = sel.rotation
		pulse_slot.origin_x = sel.origin_x + sel.width * pulse * pulse_scale / 2
		pulse_slot.origin_y = sel.origin_y + sel.height * pulse * pulse_scale / 2
		pulse_slot.alpha = 150 * ( 1.0 - pulse )

		if(( pulse_slot.alpha == 1 && my_config["wheel_pulse"] == "Once" ) || ( pulse_slot.alpha == 1 && my_config["wheel_fadeout"] != "No" ))
			pulse_once = true
	}

	fe.add_ticks_callback( "tick_pulse" )
	tick_pulse <- function( ttime )
	{
		update_pulse()
	}

	fe.add_transition_callback("transition_pulse")
	transition_pulse <- function(ttype, var, ttime)
	{
		if( ttype == Transition.ToNewSelection || ttype == Transition.ToNewList )
		{
			pulse = 0.0
			pulse_once = false
		}

		return false
	}
}



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Wheel navigation sounds

local sound_name = ""
local Wheelclick = []
sid <- 0
click_enable <- 0

for( local i = 0; i < 10; i++ )
	Wheelclick.push(fe.add_sound(sound_name))


fe.add_transition_callback("transition_wheel_sounds")
function transition_wheel_sounds(ttype, var, ttime)
{
	if( my_config["enable_nav_sound"] != "No" )
	{
		switch( ttype )
		{
			case Transition.ToNewSelection:
				if( my_config["enable_additional_sound"] == "Yes" )
				{
					if( click_enable == 0 && my_config["enable_nav_sound"] == "Random" )
					{
						// play additional click
						sid++
						if( sid > 9 ) //if reached end of the array go to the beginning
							sid = 0
						Wheelclick[sid].file_name = FeConfigDirectory+"gtc-common/sounds/hs_click.mp3"
						Wheelclick[sid].playing = true
						click_enable++
					}
				}
			break

			case Transition.StartLayout:
			case Transition.EndNavigation:
				if( ttype == Transition.StartLayout && my_config["wheel_entry_anim"] == "Yes" )
				{
					Wheelclick[sid].file_name = FeConfigDirectory+"gtc-common/sounds/Sound_Wheel_In.mp3"
					Wheelclick[sid].playing = true
					click_enable = 0
					break
				}

				sid++ // next cell in the array
				if( sid > 9 )
					sid = 0

				if( my_config["enable_nav_sound"] == "Random" )
					Wheelclick[sid].file_name = FeConfigDirectory+"gtc-common/sounds/GS"+random(1, 322)+".mp3"

				if( my_config["enable_nav_sound"] == "Click" )
					Wheelclick[sid].file_name = FeConfigDirectory+"gtc-common/sounds/click.mp3"

				if( my_config["enable_nav_sound"] == "Arcade Joystick" )
					Wheelclick[sid].file_name = FeConfigDirectory+"gtc-common/sounds/joystick.mp3"

				Wheelclick[sid].playing = true

				click_enable = 0
			break
		}
	}
	return false
}



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Hyperspin special animations

if( my_config["enable_hs_special"] == "Yes" )
{
	/*local top_h = fe.add_image("white.png", 0, flh * 0.931, flw, 2 )
	top_h.set_rgb(0,255,0)
	local bottom_h = fe.add_image("white.png", 0, flh * 0.968, flw, 2 )
	bottom_h.set_rgb(0,255,0)*/

	current_sidetxt <- 2
	current_joy_anim <- 1
	new_joy_anim <- 1
	start_anims_delay <- true
	first_animation <- true
	animate_counter <- 0
	center_text_y <- 0


	// Side text
	local side_text = fe.add_image("text/free play.png", flw*0.046, flh*1.5, flw*0.91, flh*0.0462)
	side_text.mipmap = true
	side_text.zorder = 30
	side_text = Inertia(side_text, 1000, "x", "y")

	// Center text
	local center_text = fe.add_image( "", 0, flh * 1.5, 0, 0 )
	center_text.mipmap = true
	center_text.zorder = 30
	center_text = Inertia(center_text, 1000, "x", "y")

	// Joystick
	local joystick = AnimatedJoystick( my_config["joystick_color"].tolower(), AnimatedJoystickDirection.Neutral )
	joystick.style = my_config["joystick_style"].tolower()
	joystick.x = flw - flw / 1.7
	joystick.y = flh * 1.5
	joystick.width = flw * 0.043
	joystick.time = 500
	joystick = Inertia(joystick, 1000, "x", "y")


	if( my_config["set_perspective"] == "Full Screen" )
	{
		switch( aspect_name )
		{
			case "16x9":
				joystick.width = flw * 0.033
			break
			case "16x10":
				joystick.width = flw * 0.037
			break
			case "4x3":
				joystick.width = flw * 0.044
			break
			case "5x4":
				joystick.width = flw * 0.045
			break
			case "21x9":
				joystick.width = flw * 0.025
			break
			default:   // 16x9
				joystick.width = flw * 0.033
			break
		}
	}


	// sideline text timers
	flickering_speed <- 40
	side_text_timer <- flickering_speed
	side_text.subimg_height = side_text.texture_height / 4.0

	// joystick timers
	anim_delay <- 600
	delay_time <- anim_delay
	reload_animations_delay <- 5000
	reload_animations_play <- reload_animations_delay


	fe.add_ticks_callback( "ticks_hs_special" )
	ticks_hs_special <- function( tick_time )
	{
		// sideline texts
		if( tick_time >= side_text_timer )
		{
			side_text.subimg_y += side_text.texture_height / 4.0

			if( side_text.subimg_y >= side_text.texture_height )
				side_text.subimg_y = 0

			side_text_timer = tick_time + flickering_speed
		}

		// reload animations every 'reload_animations_delay' milliseconds
		if( tick_time >= reload_animations_delay  )
		{
			// don't repeat same type of joystick animation
			while( current_joy_anim == new_joy_anim )
				new_joy_anim = random(1, 2)

			current_joy_anim = new_joy_anim
			animate_counter++

			// animate
			joystick.to_y = flh * 1.5
			center_text.to_y = flh * 1.5
			if( animate_counter > 2 || first_animation )
				side_text.to_y = flh * 1.5

			start_anims_delay = true
		}

		// delay start of animations when off-screen
		if( start_anims_delay )
		{
			anim_delay = tick_time + delay_time
			reload_animations_delay = tick_time + reload_animations_play
			start_anims_delay = false
		}


		if( tick_time >= anim_delay )
		{
			// update joystick animation type only when off-screen
			if( joystick.y > flh * 1.2 )
			{
				switch( current_joy_anim.tostring() )
				{
					case "1":
						joystick.direction = AnimatedJoystickDirection.Down  // next system
						joystick.x = flw - flw / 1.631

						center_text.file_name = "text/next system.png"
						center_text.x = joystick.x + flw * 0.042
						center_text_y = flh * 0.93
						center_text.width = flw * 0.4895 * 0.42
						center_text.height = flh * 0.1629 * 0.294
					break
					case "2":
						joystick.direction = AnimatedJoystickDirection.Up  // previous system
						joystick.x = flw - flw / 1.579

						center_text.file_name = "text/previous system.png"
						center_text.x = joystick.x + flw * 0.037
						center_text_y = flh * 0.924
						center_text.width = flw * 0.4895 * 0.52
						center_text.height = flh * 0.1629 * 0.347
					break
					default:
						joystick.direction = AnimatedJoystickDirection.Down  // next system
						joystick.x = flw - flw / 1.631

						center_text.file_name = "text/next system.png"
						center_text.x = joystick.x + flw * 0.042
						center_text_y = flh * 0.93
						center_text.width = flw * 0.4895 * 0.42
						center_text.height = flh * 0.1629 * 0.294
					break
				}
			}

			// animate
			if( animate_counter > 2 || first_animation )
			{
				if( current_sidetxt == 1 )
				{
					side_text.file_name = "text/press start.png"
					side_text.subimg_height = side_text.texture_height /4
					current_sidetxt = 2
				}
				else
				{
					side_text.file_name = "text/free play.png"
					side_text.subimg_height = side_text.texture_height /4
					current_sidetxt = 1
				}

				side_text.to_y = flh * 0.93

				animate_counter = 0
				first_animation = false
			}

			joystick.to_y = flh * 0.97
			center_text.to_y = center_text_y
		}
	}

	fe.add_transition_callback( "transition_hs_special" )
	transition_hs_special <- function( ttype, var, ttime )
	{
		switch( ttype )
		{
			case Transition.StartLayout:
				// start layout with next game joystick animation
				current_joy_anim = 1
			break
			case Transition.ToNewList:
			case Transition.EndNavigation:
				// hide side texts when on following slots
				/*local sys = fe.game_info(Info.Title, var)
				if( sys == "Ingame Settings" || sys == "Controls" || sys == "Credits" || sys == "Exit HyperSpin" )
					side_text.visible = false
				else
					side_text.visible = true*/
			break
		}
		return false
	}
}



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Letters

local trigger_letter = false
local letters = fe.add_image("", flw * 0.5 - (flw*0.120 * 0.5), flh * 0.5 - (flh*0.240 * 0.49), flw*0.120, flh*0.240)  // default
letters.preserve_aspect_ratio = true

if( my_config["letters_type"] == "White" )
{
	letters.preserve_aspect_ratio = false
	letters.x = flw * 0.5 - (flw*0.1 * 0.5)
	letters.y = flh * 0.5 - (flh*0.17 * 0.5)
	letters.width = flw*0.1
	letters.height = flh*0.17
}


fe.add_transition_callback( "letter_transition" )
function letter_transition( ttype, var, ttime )
{
	if( ttype == Transition.ToNewList )
		rtime = glob_time

	return false
}

fe.add_ticks_callback( "letter_tick" )
function letter_tick( ttime )
{
	glob_time = ttime

	if( glob_time - rtime > glob_delay )
		letters.visible = false // hide letter search if present

    if( trigger_letter == true )
	{
		local firstl = fe.game_info(Info.Title)

		if( my_config["letters_type"] != "No" )
		{
			if( my_config["letters_type"] == "Default" )
				letters.file_name = FeConfigDirectory + "gtc-common/letters/default/" + firstl.slice(0,1) + ".png"
			else  //white
				letters.file_name = FeConfigDirectory + "gtc-common/letters/white/" + firstl.slice(0,1) + ".png"

			letters.visible = true
		}
		trigger_letter = false
    }
}

fe.add_signal_handler( "on_signal_letters" )
function on_signal_letters(str)
{
	switch( str )
	{
		case "next_letter":
		case "prev_letter":
			rtime = glob_time
			trigger_letter = true
		break
	}

    return false
}



//////////////////////////////////////////////////////////////////////////////////////////////////
// Ambient sound / Music

song_title <- fe.add_text( "", flx*0.1, fly*-1.2, flw*0.8, flh*0.05 )
song_title.set_rgb( 255, 255, 0 )
song_title.charsize = font_size*0.8

fe.do_nut( FeConfigDirectory+"gtc-common/nut/jukebox.nut" )



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Exit overlay menu

// overlay surface
local overlay_surface = fe.add_surface(flw, flh)
overlay_surface.visible = false
overlay_surface.zorder = 40

// overlay background
local overlay_background = overlay_surface.add_image( "images/Menu_Exit_Background.png", 0, 0, flw, flh )

// overlay menu surface
local overlay_menusurface = overlay_surface.add_surface(flw, flh)
overlay_menusurface.set_pos(0, 0)

// overlay menu list box
local overlay_listbox = overlay_menusurface.add_listbox( flw*0.369, flh*0.361, flw*0.260, flh*0.370 )
overlay_listbox.rows = 3
overlay_listbox.set_rgb(255, 255, 255)
overlay_listbox.font = "SF Slapstick Comic Bold Oblique.ttf"
overlay_listbox.charsize = flw*0.052
overlay_listbox.align = Align.MiddleCentre
overlay_listbox.selbg_alpha = 0
overlay_listbox.set_sel_rgb(255, 0, 0)

// overlay menu title
local overlay_menutitle = overlay_menusurface.add_text( "", flw*0.346, flh*0.324, flw*0.312, flh*0.046 )

// tell attract-mode we are using a custom overlay menu
fe.overlay.set_custom_controls( overlay_menutitle, overlay_listbox )

old_alpha <- 0

// show or hide the exit overlay menu
fe.add_transition_callback( "transition_exit_overlay" )
function transition_exit_overlay( ttype, var, ttime )
{
	switch( ttype )
	{
		case Transition.ShowOverlay:
			overlay_menutitle.msg = ""
			overlay_surface.visible = true
			if( ttime < 255 )
			{
				overlay_surface.alpha = ttime
				return true
			}
			else
			{
				overlay_surface.alpha = 255
			}
		break
		case Transition.HideOverlay:
			if( ttime < 255 )
			{
				overlay_surface.alpha = 255 - ttime
				return true
			}
			else
			{
				old_alpha = overlay_surface.alpha
				overlay_surface.alpha = 0

				if( old_alpha != 0 )
					return true
			}
			overlay_surface.visible = false
		break
	}
	return false
}

// Stops menu selection
function on_signal_menu( sig )
{
    switch( sig )
    {
        case "select":
			if( fe.game_info( Info.Title ) == "Controls" )
			return true

        case "select":
			if( fe.game_info( Info.Title ) == "Credits" )
			return true

        default:
            return false
    }
}
fe.add_signal_handler( "on_signal_menu" )



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Scanlines and aperture

if( my_config["enable_scanlines"] == "Scanlines" )
{
	local scanlines = FeConfigDirectory+"gtc-common/art/scanlines_1920.png"
	if( ScreenWidth < 1920 )
		scanlines = FeConfigDirectory+"gtc-common/art/scanlines_720.png"

	local masking = fe.add_image( scanlines, 0, 0, flx, fly )
	masking.preserve_aspect_ratio = false
	masking.alpha = 45
	masking.zorder = 40
}

if( my_config["enable_scanlines"] == "Aperture" )
{
	local masking = fe.add_image( "aperture.png", 0, 0, flx, fly )
	masking.preserve_aspect_ratio = false
	masking.alpha = 100
	masking.zorder = 40
}



////////////////////////////////////////////////////////////////////////////////////////////////////////
// Screen Bezel

if( my_config["enable_bezel"] != "No" && my_config["set_perspective"] == "4x3" )
{
	if( aspect_name == "21x9" && my_config["force_bezels"] == "No" )
	{
		local left_cover = fe.add_image(FeConfigDirectory+"gtc-common/art/arcade/vertical_cover.png", flx*-0.4, 0, flw*0.25, flh)
		local right_cover = fe.add_image(FeConfigDirectory+"gtc-common/art/arcade/vertical_cover.png", flx*1.15, 0, flw*0.25, flh)

		left_cover.zorder = 40
		right_cover.zorder = 40
	}

	if( aspect_name == "5x4" && my_config["force_bezels"] == "No" )
	{
		local top_cover = fe.add_image(FeConfigDirectory+"gtc-common/art/arcade/vertical_cover.png", 0, fly*-0.1, flw, flh*0.1)
		local bottom_cover = fe.add_image(FeConfigDirectory+"gtc-common/art/arcade/vertical_cover.png", 0, fly*1.0, flw, flh*0.1)

		top_cover.zorder = 40
		bottom_cover.zorder = 40
	}

	local bezel
	local bezel_type = my_config["enable_bezel"]

	switch( bezel_type )
	{
		case "Attractmode":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/attractmode.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "Attractmode Framed":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/attractmode_framed.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "MAME":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/mame.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "MAME Framed":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/mame_framed.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "MAME2":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/mame2.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "MAME Framed2":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/mame_framed2.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "Cool Arcade":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/cool_arcade.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "Real Arcade":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/real_arcade.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "Arcade Classics":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/arcade_classics.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "Arcade Classics Framed":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/arcade_classics_framed.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "TV":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/tv.png", flx*-0.167, 0,flw*1.334,flh)
		break
		case "TV Framed":
			bezel = fe.add_image(FeConfigDirectory+"gtc-common/bezels/tv_framed.png", flx*-0.167, 0,flw*1.334,flh)
		break
	}
	bezel.zorder = 42
}


// print to console time it took to load layout
print ( format( "Main menu layout loaded in: %u ms\n", (::clock() - layout_t) * 1000 ))
