////////////////////////////////////////////////////////////////////////////////////////////////////////
/* NEC TurboGrafx-16  v10.4

░█▀█░█▀▀░█▀▀░░░▀█▀░█░█░█▀▄░█▀▄░█▀█░█▀▀░█▀▄░█▀█░█▀▀░█░█░░░░░▀█░░▄▀▀
░█░█░█▀▀░█░░░░░░█░░█░█░█▀▄░█▀▄░█░█░█░█░█▀▄░█▀█░█▀▀░▄▀▄░▄▄▄░░█░░█▀▄
░▀░▀░▀▀▀░▀▀▀░░░░▀░░▀▀▀░▀░▀░▀▀░░▀▀▀░▀▀▀░▀░▀░▀░▀░▀░░░▀░▀░░░░░▀▀▀░░▀░

Design, Code and Art by Yaron */
////////////////////////////////////////////////////////////////////////////////////////////////////////



local layout_t = clock()
local orderx = 0
local divider = "----"

class UserConfig {
	</ label="Enable startup animations", help="Enable system animation when layout starts",
		options="Yes,No", order=orderx++ /> enable_ini_anim="Yes"
	</ label="Startup animation transition time", help="animation time in ms",
		options="500,1000,1500,2000", order=orderx++ />ini_anim_trans_ms="1000"
	</ label="Enable background scanlines", help="Show scanlines effect on background image",
		options="No,Light,Medium,Strong", order=orderx++ /> enable_bg_scanline="No"
	</ label= divider, help=" ", options = " ", order=orderx++ /> paramxx0 = " "

	</ label="Enable music", help="Play music from the configured music folder",
		options="No,Music", order=orderx++ /> enable_ambience="No"
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
	</ label=divider, help=" ", options = " ", order=orderx++ /> paramxx1 = " "

	</ label="Type of wheel", help="Select round wheel or vertical wheel",
		options="Round,Vertical", order=orderx++ /> wheel_type="Round"
	</ label="Number of wheel slots", help="Number of slots in the wheel",
		options="5,7,9,11,13,15,17", order=orderx++ />wheel_slots="9"
	</ label="Wheel speed", help="wheel spin speed",
		options="100,200,300,600,1200", order=orderx++ /> transition_ms="300"
	</ label="Preserve wheel logo's aspect ratio", help="Preserve the original aspect ratio of the wheel logos, great for vertical wheel mode",
		options="Yes,No", order=orderx++ /> wheel_logo_aspect="Yes"
	</ label="Adjust wheel position", help="Adjust wheel position closer to or further from the right side of the screen",
		options="Adjust Left,Adjust Right", order=orderx++ /> wheel_poisition="Adjust Right"
	</ label="Enable wheel fadeout", help="Enable wheel fadeout",
		options="No,Partially,Completely", order=orderx++ /> wheel_fadeout="Partially"
	</ label="Fade wheel time", help="Fade wheel time",
		options="500,1000,2000,3000", order=orderx++ /> wheel_fade_ms="500"
	</ label="Delay time", help="The time (in milliseconds) it takes to start hiding the wheel and pointer",
		options="500,1000,1500,2000", order=orderx++ /> set_ms_delay="1000"
	</ label="Enable wheel pulse", help="Current wheel selection art will pulse once or in a loop",
		options="No,Once,Loop", order=orderx++ /> wheel_pulse="Once"
	</ label="Enable wheel background", help="Show wheel background texture",
		options="No,Light,Medium,Dark", order=orderx++ /> enable_wl_bg="No"
	</ label="Enable wheel sounds", help="Play sounds when navigating games wheel",
		options="No,Random,Click", order=orderx++ /> enable_nav_sound="Random"
	</ label="Enable wheel pointer", help="Show animated wheel pointer",
		options="Yes,No", order=orderx++ /> enable_pointer="No"
	</ label="Enable letters",
		help="Show graphical letters on the screen when pressing the wheel's 'Next Letter' or 'Previous Letter' hotkeys set in the Controls menu.\n 'System Display Name' option will seek the letters in a folder identical to the current system display name (attract/letters/mame for example).",
		options="No,Default,White,By System Display Name", order=orderx++ /> letters_type="Default"
	</ label=divider, help=" ", options=" ", order=orderx++ /> paramxx2=" "

	</ label="Enable CRT scanlines", help="Show CRT scanlines",
		options="None,Light,Medium,Dark", order=orderx++ /> enable_crt_scanline="Light"
	</ label="Enable CRT bloom shader effect", help="Creates a bloom effect for the snap video, if device is able to run GLSL shaders",
		options="Yes,No", order=orderx++ /> enable_bloom="No"
	</ label="Mute game snap videos", help="Mute game snap videos",
		options="Yes,No", order=orderx++ /> mute_videos="No"
	</ label= divider, help=" ", options = " ", order=orderx++ /> paramxx3 = " "

	</ label="Show game box art", help="Shows the current game box art if available",
		options="Yes,No", order=orderx++ /> enable_gboxart="Yes"
	</ label="Show game cart art", help="Shows the current game cart art if available",
		options="Yes,No", order=orderx++ /> enable_gcartart="Yes"
	</ label= divider, help=" ", options = " ", order=orderx++ /> paramxx4 = " "

	</ label="Show game information", help="Show game info",
		options="No,Info,Info and Enumerate", order=orderx++ /> enable_gameinfo="Info and Enumerate"
	</ label="Game name", help="Show game title only or manufacturer and game title. If there is no manufacturer name in the romlist, only the game title will be shown.",
		options="Title Only,Manufacturer and Title", order=orderx++ /> enable_game_manu="Title Only"
	</ label="Enable random text colors", help="Enable game info random text colors",
		options="Yes,No", order=orderx++ /> enable_colors="No"
	</ label="Enable text frame", help="Show frame to make game info text standout ",
		options="Yes,No", order=orderx++ /> enable_frame="Yes"
	</ label= divider, help=" ", options = " ", order=orderx++ /> paramxx5 = " "

	</ label="Mark favourite games", help="Mark favourite games with an icon to the sides of the wheel or at the bottom with the game info",
		options="No,Left of Wheel,Right of Wheel,With Game Info", order=orderx++ /> enable_favstar="Right of Wheel"
	</ label= divider, help=" ", options = " ", order=orderx++ /> paramxx6= " "

	</ label="Search key", help="Choose the key to initiate a search",
		options="Custom1,Custom2,Custom3,Custom4,Custom5,Custom6", order=orderx++ /> user_search_key="Custom1"
	</ label="Search box size", help="Choose size of the search box",
		options="Small,Large", order=orderx++ /> user_search_boxsize="Small"
	</ label= divider, help=" ", options = " ", order=orderx++ /> paramxx7 = " "
}
my_config <- fe.get_config()



// modules
fe.load_module("wheel")
fe.load_module("animate")
fe.load_module("fade")
fe.load_module("file")
fe.load_module("file-format")
fe.load_module("gtc")
fe.load_module("gtc-pas")
fe.load_module("gtc-kb")
fe.load_module("favorites")
fe.load_module("img_fade_in")



//////////////////////////////////////////////////////////////////////////////////////////////////
// Initializations

aspect_name <- ""

fe.do_nut( FeConfigDirectory+"gtc-common/nut/screen_aspect.nut" )

flx <- fe.layout.width
fly <- fe.layout.height
flw <- fe.layout.width
flh <- fe.layout.height


ini_anim_time <- my_config["ini_anim_trans_ms"].tointeger()

// wheel fade timer
wheel_delay <- my_config["set_ms_delay"].tointeger()
wheel_play <- wheel_delay

function FavStar()
{
	if( check_favorite() ) return FeConfigDirectory+"gtc-common/art/arcade/fav.png"
}

function random( minNum, maxNum )
{
	return floor(((rand() % 10000 ) / 10000.0) * (maxNum - (minNum - 1)) + minNum)
}



//////////////////////////////////////////////////////////////////////////////////////////////////
// Font

fe.layout.font = "Industria_Solid"



//////////////////////////////////////////////////////////////////////////////////////////////////
// Favorites

if( fe.nv.rawin( "GLOBAL_FAVORITES_LIST_LOADED" ) )
{
	if( fe.nv["GLOBAL_FAVORITES_LIST_LOADED"] == 1 )
		update_favorites_split_list()
	else
	{
		test_romlist()
		get_favorites()
	}
}



//////////////////////////////////////////////////////////////////////////////////////////////////
// Background

local bg = fe.add_image( "bkg.jpg", 0, 0, flw, flh )
bg.zorder = -15
local img_fade = img_fade_in( bg, 6 )



//////////////////////////////////////////////////////////////////////////////////////////////////
// Background scanlines

bg_scanlines <- fe.add_image( "", 0, 0, flw, flh )
bg_scanlines.zorder = -14
fe.do_nut( FeConfigDirectory+"gtc-common/nut/bg_scanlines.nut" )



//////////////////////////////////////////////////////////////////////////////////////////////////
// Video snap

// black background if no snap video available
local snapbg = fe.add_image( FeConfigDirectory+"gtc-common/art/arcade/vertical_cover.png", flx*0.044, fly*0.24, flw*0.315, flh*0.425 )
snapbg.zorder = -13

if( my_config["enable_ini_anim"] == "Yes" )
{
	// animate static effect entry when layout starts
	local move_transition1 = {when = Transition.StartLayout, property = "x", start = flx*-1.36,	end = flx*0.044, tween = "cubic", time = ini_anim_time}
	animation.add( PropertyAnimation( snapbg, move_transition1 ) )
}

// add current game snap video
local snap = fe.add_artwork( "snap", flx*0.044, fly*0.24, flw*0.315, flh*0.425 )
snap.trigger = Transition.EndNavigation
snap.preserve_aspect_ratio = false
snap.zorder = -12

if( my_config["mute_videos"] == "Yes" )
	snap.video_flags = Vid.NoAudio

if( my_config["enable_ini_anim"] == "Yes" )
{
	// animate snap entry when layout starts
	local move_transition1 = {when = Transition.StartLayout, property = "x", start = flx*-1.36,	end = flx*0.044, tween = "cubic", time = ini_anim_time}
	animation.add( PropertyAnimation( snap, move_transition1 ) )
}

// bloom shader
if( my_config["enable_bloom"] == "Yes" && ShadersAvailable == 1 )
{
    local sh = fe.add_shader( Shader.Fragment, "bloom_shader.frag" )
	sh.set_texture_param("bgl_RenderedTexture")
	snap.shader = sh
}



//////////////////////////////////////////////////////////////////////////////////////////////////
// CRT scanlines

local scanlines = fe.add_image( "", flx*0.044, fly*0.24, flw*0.31, flh*0.5 )

if( my_config["enable_crt_scanline"] != "None" )
{
	if( ScreenWidth < 1920 )
		scanlines.file_name = FeConfigDirectory+"gtc-common/art/scanlines_640.png"
	else
		scanlines.file_name = FeConfigDirectory+"gtc-common/art/scanlines_1920.png"

	if( my_config["enable_crt_scanline"] == "Light" )
		scanlines.alpha = 30
	else if( my_config["enable_crt_scanline"] == "Medium" )
		scanlines.alpha = 60
	else if( my_config["enable_crt_scanline"] == "Dark" )
		scanlines.alpha = 150

	scanlines.zorder = -11

	if( my_config["enable_ini_anim"] == "Yes" )
	{
		local move_transition1 = {when = Transition.StartLayout, property = "x", start = flx*-1.36, end = flx*0.044, tween = "cubic",time = ini_anim_time}
		animation.add( PropertyAnimation( scanlines, move_transition1 ) )
	}
}



//////////////////////////////////////////////////////////////////////////////////////////////////
// Art images

local logo_y = fly*-1.5
if ( my_config["enable_ini_anim"] == "No" )
	logo_y = 0

local tv = fe.add_image( "tv.png", 0, 0, flw, flh )
tv.zorder = -10
if( my_config["enable_ini_anim"] == "Yes" )
{
	local move_transition1 = {when = Transition.StartLayout, property = "x", start = flx*-1.45,	end = flx*0.0, tween = "cubic",	time = ini_anim_time}
	animation.add( PropertyAnimation( tv, move_transition1 ) )
}

local logo = fe.add_image( "logo.png", 0, logo_y, flw, flh )
logo.zorder = -9
if( my_config["enable_ini_anim"] == "Yes" )
{
	local start_transition1 = {when = Transition.StartLayout, property = "y", start = fly*-2, end = fly*0, tween = "bounce", delay = ini_anim_time+200, time = ini_anim_time+800}
	animation.add( PropertyAnimation( logo, start_transition1 ) )
}


if( my_config["wheel_fadeout"] != "No" || my_config["enable_gboxart"] == "No" )
{
	local spaceship
	if ( my_config["enable_ini_anim"] == "Yes" )
	{
		spaceship = PanAndScanImage( "spaceship.png", 0, fly*1.5, flw, flh )
		spaceship.trigger = Transition.EndNavigation
		spaceship.preserve_aspect_ratio = false
		spaceship.set_fit_or_fill("fit")
		spaceship.set_anchor(::Anchor.Bottom)
		spaceship.set_zoom(0, 0)
		spaceship.set_animate(::AnimateType.Bounce, 0.1, 0.15)
		spaceship.set_start_scale(1.02)
		spaceship.zorder = -8

		local move_transition1 = {
			when = Transition.StartLayout,
			property = "position",
			start = {x = flx*-1.5, y = fly*-1.2},
			end = {x = flx*0.0, y = 0},
			tween = "cubic",
			time = ini_anim_time
		}
		animation.add( PropertyAnimation( spaceship, move_transition1 ) )
	}
	else
	{
		spaceship = fe.add_image( "spaceship.png", 0, 0, flw, flh )
		spaceship.zorder = -8
	}
}


local console = fe.add_image( "console.png", 0, 0, flw, flh )
logo.zorder = -7
if( my_config["enable_ini_anim"] == "Yes" )
{
	local move_transition1 = {when = Transition.StartLayout, property = "y", start = fly*1,	end = fly*0, tween = "cubic", time = ini_anim_time}
	animation.add( PropertyAnimation( console, move_transition1 ) )
}



//////////////////////////////////////////////////////////////////////////////////////////////////
// Cartart

if( my_config["enable_gcartart"] == "Yes" )
{
	local y = 0.698
	local x = 0.414
	if( aspect_name = "4x3" )
		x = 0.41

	local surface = fe.add_surface( 640, 480 )
	surface.set_pos( flx*0.416, fly*2.1, flw*0.13, flh*0.2 )
	surface.skew_y = -5
	surface.skew_x = 18
	if( aspect_name = "4x3" )
		surface.skew_x = 16

	local cartart = surface.add_artwork( "cartart", 0, 0, 640, 480 )
	cartart.trigger = Transition.EndNavigation
	cartart.set_rgb( 235,235,235 )
	cartart.mipmap = true
	cartart.preserve_aspect_ratio = true

	local start_transition1 = {
		when = Transition.StartLayout,
		property = "position",
		start = {x = flx*0.48, y = fly*2.1},
		end = {x = flx*x, y = fly*y},
		tween = "cubic",
		delay = ini_anim_time*0.5,
		time = ini_anim_time+500
	}
	animation.add( PropertyAnimation( surface, start_transition1 ) )

	cartart_transition <- function( ttype, var, ttime )
	{
		if( ttype == Transition.EndNavigation )
			cartart.visible = true

		if( ttype == Transition.ToNewSelection )
			cartart.visible = false

		return false
	}
	fe.add_transition_callback( "cartart_transition" )

	local move_transition1 = {
		when = Transition.EndNavigation,
		property = "position",
		start = {x = flx*0.48, y = fly*2.1},
		end = {x = flx*x, y = fly*y},
		tween = "cubic",
		time = ini_anim_time+500
	}
	animation.add( PropertyAnimation( surface, move_transition1 ) )
}



//////////////////////////////////////////////////////////////////////////////////////////////////
// Console cover and joystick

local console_cover = fe.add_image( "console_cover.png", 0, 0, flw, flh )
if( my_config["enable_ini_anim"] == "Yes" )
{
	// animate console_cover image when layout starts
	local move_transition1 = {when = Transition.StartLayout, property = "y", start = fly*1,	end = fly*0, tween = "cubic", time = ini_anim_time}
	animation.add( PropertyAnimation( console_cover, move_transition1 ) )
}

local joystick = fe.add_image( "joystick.png", 0, 0, flw, flh )
if( my_config["enable_ini_anim"] == "Yes" )
{
	local move_transition1 = {when = Transition.StartLayout, property = "y", start = fly*1,	end = fly*0, tween = "cubic", time = ini_anim_time}
	animation.add( PropertyAnimation( joystick, move_transition1 ) )
}



//////////////////////////////////////////////////////////////////////////////////////////////////
// Wheel

fe.do_nut( FeConfigDirectory+"gtc-common/nut/wheel.nut" )



//////////////////////////////////////////////////////////////////////////////////////////////////
// Boxart

if( my_config["enable_gboxart"] == "Yes" )
{
	// if wheel_fadeout != No
	local from_side = 2 //enter from right
	local x = 0.68
	local y = 0.35
	local w = 0.21
	local h = 0.6

	if( my_config["wheel_fadeout"] == "No" )
	{
		x = 0.33
		y = 0.18
		w = 0.21
		h = 0.51
		if (aspect_name == "16x10")
			x = 0.34
	}

	local boxart = fe.add_artwork("boxart", flx*x, fly*y, flw*w, flh*h )
	boxart.trigger = Transition.EndNavigation
	boxart.preserve_aspect_ratio = true
	boxart.zorder = 10

	if( my_config["wheel_fadeout"] == "No" )
		boxart.zorder = -8

	local start_transition1 = {when = Transition.StartLayout, property = "x", start = flx*from_side, end = flx*x, time = wheel_delay+200}
	animation.add( PropertyAnimation( boxart, start_transition1 ) )

	boxart_transition <- function( ttype, var, ttime )
	{
		if( ttype == Transition.EndNavigation )
			boxart.visible = true

		if( ttype == Transition.ToNewSelection )
			boxart.visible = false

		return false
	}
	fe.add_transition_callback( "boxart_transition" )

	local move_transition1 = {when = Transition.EndNavigation, property = "x", start = flx*from_side, end = flx*x, time = wheel_delay+200}
	animation.add( PropertyAnimation( boxart, move_transition1 ) )
}



//////////////////////////////////////////////////////////////////////////////////////////////////
// Game info background frame

fe.do_nut( FeConfigDirectory+"gtc-common/nut/game_info_frame.nut" )



//////////////////////////////////////////////////////////////////////////////////////////////////
// Favourite marker for "With Game Info" setting, separated from Wheel to avoid zorder issues

fav_x <- flx*0.069
fav_y <- fly*0.95
fav_wh <- flw*0.022

fe.do_nut( FeConfigDirectory+"gtc-common/nut/game_info_fav_marker.nut" )



//////////////////////////////////////////////////////////////////////////////////////////////////
// Game info

font_size <- flh*0.0335

year_b_pos <- [flx*0.009, fly*0.92, flw*0.4, flh*0.1]
year_pos <- [flx*0.01, fly*0.92, flw*0.4, flh*0.1]

title_b_pos <- [flx*0.109, fly*0.92, flw*0.7, flh*0.1]
title_pos <- [flx*0.11, fly*0.92, flw*0.7, flh*0.1]

gcount_b_pos <- [flx*0.589, fly*0.92, flw*0.4, flh*0.1]
gcount_pos <- [flx*0.59, fly*0.92, flw*0.4, flh*0.1]

rgb <- [255, 200, 0]

fe.do_nut( FeConfigDirectory+"gtc-common/nut/game_info.nut" )



//////////////////////////////////////////////////////////////////////////////////////////////////
// Ambient sound / Music

song_title <- fe.add_text( "", flx*0.1, fly*-1.2, flw*0.8, flh*0.05 )
song_title.set_rgb(rgb[0], rgb[1], rgb[2])
song_title.charsize = font_size

fe.do_nut( FeConfigDirectory+"gtc-common/nut/jukebox.nut" )



//////////////////////////////////////////////////////////////////////////////////////////////////
// Letters

fe.do_nut( FeConfigDirectory+"gtc-common/nut/letters.nut" )



//////////////////////////////////////////////////////////////////////////////////////////////////
// Search

fe.do_nut( FeConfigDirectory+"gtc-common/nut/search.nut" )



//////////////////////////////////////////////////////////////////////////////////////////////////
// System games count

fe.do_nut( FeConfigDirectory+"gtc-common/nut/game_count.nut" )



// print to console time it took to load layout
print( format( "Layout loaded in: %u ms\n", (::clock() - layout_t) * 1000 ))
