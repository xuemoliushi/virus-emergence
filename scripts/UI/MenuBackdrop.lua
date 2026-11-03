-- Runtime counterpart of the HD menu art draft. Baked material highlights stay in the image;
-- particles and breathing use UI transforms, without global Bloom or gameplay random state.
local UI = require("urhox-libs/UI")
local Backdrop = {}
-- Alpha>20 bounds measured from the full 1254px canvases. Keep their original anchors.
local SOURCE = {
    ["healthy-hd-v1.png"]={extent=901,dx=26.5,dy=-17.5},
    ["macrophage-v1.png"]={extent=1030,dx=24,dy=11},
    ["tcell-v1.png"]={extent=739,dx=0,dy=2.5},
}

---@param motion boolean
---@return Panel root
---@return Panel camera
---@return {widget:Panel,depth:number}[] layers
function Backdrop.Build(motion)
    local layers={}
    local function layer(widget,depth)
        local group=UI.Panel {position="absolute",left=0,top=0,width="100%",height="100%",
            transformOrigin="center",pointerEvents="none",children={widget}}
        layers[#layers+1]={widget=group,depth=depth}
        return group
    end
    local children = {
        UI.Panel { position="absolute", left=0, top=0, width="100%", height="100%",
            backgroundImage="image/menu/tissue-menu-v1.png", backgroundFit="cover",
            imageTint={210,210,220,255}, pointerEvents="none" },
    }
    children[1]=layer(children[1],0.16)
    local poses = {
        {95,105,430,4,0.78,"healthy-hd-v1.png"}, {1080,364,305,20,0.95,"healthy-hd-v1.png"},
        {185,610,205,39,0.80,"healthy-hd-v1.png"}, {1130,80,76,10,0.30,"healthy-hd-v1.png"},
        {1010,665,110,29,0.30,"healthy-hd-v1.png"}, {350,370,63,49,0.22,"healthy-hd-v1.png"},
        {1090,615,96,0,0.42,"macrophage-v1.png"}, {275,480,65,0,0.35,"tcell-v1.png"},
    }
    for i,pose in ipairs(poses) do
        -- Whole source canvas retained: the HD image has transparent margins around the cell.
        local source=SOURCE[pose[6]]
        local ratio=pose[3]/source.extent
        local size=1254*ratio
        local angle=pose[4]*math.pi/180
        local dx=(source.dx*math.cos(angle)-source.dy*math.sin(angle))*ratio
        local dy=(source.dx*math.sin(angle)+source.dy*math.cos(angle))*ratio
        local cell = UI.Panel { position="absolute",
            left=tostring((pose[1]-size/2-dx)/1280*100).."%",
            top=tostring((pose[2]-size/2-dy)/720*100).."%",
            width=tostring(size/1280*100).."%", aspectRatio=1,
            rotate=pose[4], opacity=pose[5], backgroundImage="image/menu/"..pose[6],
            backgroundFit="contain", imageTint={225,220,225,255}, pointerEvents="none" }
        if motion then
            cell:Animate { keyframes={ [0]={translateY=-4,scale=0.991},
                [1]={translateY=5,scale=1.009} }, duration=4+i*0.43,
                loop=true, direction="alternate", easing="easeInOut" }
        end
        children[#children+1]=layer(cell,({1.35,0.85,1.1,0.28,0.34,0.25,0.5,0.45})[i])
    end
    local seed=7319
    local function random()
        seed=(seed*1664525+1013904223)%4294967296
        return seed/4294967296
    end
    local count=0
    local moteGroups={{},{},{}}
    for _=1,110 do
        local x,y=24+random()*1232,16+random()*688
        if not (x>440 and x<840 and y>96 and y<645) and count<72 then
            count=count+1
            local size=2+random()*2.5
            local color=count%5==0 and {100,190,210,220}
                or count%3==0 and {255,160,85,220} or {240,100,125,210}
            local mote=UI.Panel {position="absolute",left=tostring(x/1280*100).."%",
                top=tostring(y/720*100).."%",width=size,height=size,borderRadius=size,
                backgroundColor=color,opacity=0.45,pointerEvents="none"}
            if motion then
                mote:Animate {keyframes={ [0]={opacity=0.07,translateY=0},
                    [0.55]={opacity=0.15,translateY=-1},[0.8]={opacity=0.85,translateY=-3},
                    [1]={opacity=0.07,translateY=0} },duration=2.5+random()*6,
                    loop=true,easing="easeInOut"}
            end
            local group=count%3+1
            moteGroups[group][#moteGroups[group]+1]=mote
        end
    end
    for i,points in ipairs(moteGroups) do
        children[#children+1]=layer(UI.Panel {position="absolute",left=0,top=0,
            width="100%",height="100%",pointerEvents="none",children=points},0.3+i*0.35)
    end
    children[#children+1]=UI.Panel {position="absolute",left=0,top=0,width="100%",height="100%",
        backgroundGradient={type="radial",innerRadius=50,outerRadius=480,
            from={3,2,7,210},to={3,2,7,10}},pointerEvents="none"}
    local camera=UI.Panel {id="menuCamera",position="absolute",left=0,top=0,
        width="100%",height="100%",transformOrigin="center",scale=1,
        pointerEvents="none",children=children}
    return UI.Panel {id="menuBackdrop",position="absolute",left=0,top=0,width="100%",
        height="100%",overflow="hidden",pointerEvents="none",children={camera}},camera,layers
end

return Backdrop
