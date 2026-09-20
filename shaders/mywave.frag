#version 440
// GPL-3.0. GLSL adaptation of yamusic visualizer_gpu.rs: simplex-noise
// lobes, orbiting layers and audio response. See NOTICE.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float phase;
    float amplitude;
    float glow;
    vec2 viewport;
    vec4 tint1;
    vec4 tint2;
    vec4 tint3;
};
vec4 perm(vec4 v) { return mod(((v * 34.0) + 1.0) * v, 289.0); }
float simplex3(vec3 pos) {
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i = floor(pos + dot(pos, C.yyy));
    vec3 x0 = pos - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz), l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy), i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0-i1+C.xxx, x2 = x0-i2+C.yyy, x3 = x0-D.yyy;
    i = mod(i,289.0);
    vec4 h0 = perm(perm(perm(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
    vec3 ns = (1.0/7.0)*D.wyz-D.xzx;
    vec4 j = h0-49.0*floor(h0*ns.z*ns.z);
    vec4 x_ = floor(j*ns.z), y_ = floor(j-7.0*x_);
    vec4 x = x_*ns.x+ns.yyyy, y = y_*ns.x+ns.yyyy;
    vec4 h = 1.0-abs(x)-abs(y);
    vec4 b0 = vec4(x.xy,y.xy), b1 = vec4(x.zw,y.zw);
    vec4 s0 = floor(b0)*2.0+1.0, s1 = floor(b1)*2.0+1.0;
    vec4 sh = -step(h,vec4(0.0));
    vec4 a0 = b0.xzyw+s0.xzyw*sh.xxyy, a1 = b1.xzyw+s1.xzyw*sh.zzww;
    vec3 q0=vec3(a0.xy,h.x),q1=vec3(a0.zw,h.y),q2=vec3(a1.xy,h.z),q3=vec3(a1.zw,h.w);
    vec4 norm=inversesqrt(vec4(dot(q0,q0),dot(q1,q1),dot(q2,q2),dot(q3,q3)));
    q0*=norm.x; q1*=norm.y; q2*=norm.z; q3*=norm.w;
    vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),vec4(0.0));
    m*=m;
    return 42.0*dot(m*m,vec4(dot(q0,x0),dot(q1,x1),dot(q2,x2),dot(q3,x3)));
}
vec2 spin(vec2 v,float a) { return mat2(cos(a),sin(a),-sin(a),cos(a))*v; }
void main() {
    vec2 uv=(qt_TexCoord0*2.0-1.0)*viewport/max(min(viewport.x,viewport.y),1.0)*1.35;
    uv.y=-uv.y;
    vec3 top[3]=vec3[3](tint1.rgb,tint2.rgb,tint3.rgb);
    vec3 bottom[3]=vec3[3](mix(tint1.rgb,tint2.rgb,0.4),mix(tint2.rgb,tint1.rgb,0.4),mix(tint3.rgb,tint2.rgb,0.22));
    vec3 orbit[3]=vec3[3](vec3(0.5,0.5,0.2),vec3(0.2,0.8,-0.3),vec3(0.8,0.2,0.4));
    vec3 color=vec3(0.0); float alpha=0.0;
    for(int i=0;i<3;i++) {
        float off=1.57*float(i);
        float response=amplitude*(1.2-0.2*float(i));
        vec2 pos=uv*(1.0-response*0.22)+spin(orbit[i].xy,phase*orbit[i].z)*0.48;
        float n=simplex3(vec3(pos*1.2+off,phase*0.5+off))*0.5+0.5;
        float radius=length(pos);
        float edge=n+0.1+(sin(phase+off)+1.0)*0.6;
        // Explicit reversed smoothstep: GLSL leaves edge0 > edge1 undefined.
        float mask=1.0-smoothstep(n,max(n+0.001,edge),radius);
        mask*=1.0-smoothstep(0.5,1.8+0.25*response,length(uv));
        float dist=abs(radius-n);
        float light=(0.1+0.15*response)/(1.0+dist+10.0*dist*dist);
        vec3 col=mix(top[i],bottom[i],clamp(pos.y*2.0,0.0,1.0))*(1.0+light);
        color=mix(color,col,mask); alpha=mask+alpha*(1.0-mask);
    }
    color+=vec3(0.6,0.32,0.8)*glow*exp(-dot(uv,uv)*1.5)*alpha;
    fragColor=vec4(min(color,vec3(alpha)),alpha)*qt_Opacity;
}
