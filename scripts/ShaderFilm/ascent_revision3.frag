#version 300 es
precision highp float;
in vec2 vUV;
uniform sampler2D uTex;
uniform vec2 uResolution;
uniform float uScale;
uniform float uHorizon;
uniform float uSourceHorizon;
uniform float uOpacity;
out vec4 frag;
void main(){
 // A full-screen inverse projection has no shrinking card or feathered border.
 // Source horizons align to one continuously moving on-screen horizon.
 vec2 source=(vUV*uResolution-vec2(960.,uHorizon))/uScale+vec2(960.,uSourceHorizon);
 vec3 c=texture(uTex,source/uResolution).rgb;
 float gray=dot(c,vec3(.299,.587,.114));
 c=mix(c,vec3(gray)*vec3(1.025,1.012,.982),.35);
 frag=vec4(c,uOpacity);
}
