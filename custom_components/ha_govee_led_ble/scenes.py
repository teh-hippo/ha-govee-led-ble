"""H617A scene catalogue — generated from Govee API for H617A."""

import base64
import json
import zlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SceneEntry:
    code: int
    param: str = ""
    scene_type: int = 2  # multi-frame body prefix: 2 (default), 0 (simple), 1 (e.g. Halloween/Sweet)

    @property
    def is_simple(self) -> bool:
        return not self.param


_SCENES_PAYLOAD = "c$~FbNps>#68<ZWzRZD+D0aj|yhD{%o-G@BYvYMI02YNTK(xS?VPgLKWY#9JxZQ6ih6tKA&aBMJ^~;q1^=<RE%9Bm}?eG7nfB*LFd;Oo^@vBX|g>M@An^~5}8~mo(=(fIpqq`BM5xt~5Ab#Z6ZJyaX7I}nNln#k_;pbv#QIGmRD8B5FQf_(3<I$i8->@3bTn02-c;5m~8~OE%W#V6?XHhWlSY-F+5u?Kj4gKSfZ{M4s;P@@i^08E~4GJdIFo)a~Kh$0aj$j7Ge!jzJVN;_RrH;Ie)5ULUoVqhm1}~Hi<z+x=_?<&ap^Jpix2t5urQ8n4y<37zSIDIl-jQpQUFZvg!0Y(ai=IL^db%#p+-%2rzPs3@J9%i=T*k%&{m5&FuLFDMz-3UGphu)qw7d+r9Hd2s(Q4#=;3AC>db2;IF9ol2bCVvrIE8~UPg+GD4Hopto>S67D=IgDWs(99tXOm2zC;B`A-#asv?BUKS`QRGOzImdl>m#fy7UxvckuH-UCzey2|4HL&D(Mr=TcD%6rGoGq6AX1AFvQ_Yg{}!R*HgBo=^hg6_pago|I*(Zk~-73n{Muxj3{-DK0%H&Of$+{+&ym>7mFXS#8xFdytm&qZDd$$OW2F@G2t*cPtGLPUqlxMk4AW%@*G4cS2r>2;+ep1$_w1GxXUBJ<twZ9$2Mv`8ZikvI4bhngWsJu~Zjo2D=qLg|zpIkl*w$2phK$h>bLmDm%o*n7K<=m;`vOWpqWJKHBJaUuOtu)&o+9chQD7|I_7;<zk#A=^RM>-{zxE4c>j4EF3zI9;9DvidXK=BcFUc2s-iJfsV!WUihVOED_hcG?g(Lh&UH~w~B8M^lgySXbV14Sb<kK9rPzF{W*SD=4oP)2u(h#5HL9^@>%7mTLji&=)c7A`eGByI@iNOJlEM%Mp_HA$G<;Jb1bGj69IHdgC`l|11P4oAEz0Xj`Pj-Vrq15A6I-Y)fN9eg1S;qDd~*p3W}<Sg_3(|B@Kqi^Gt)KC<S0{Hk9Q9%Lb{x6G)5rAk}3+!=?NmA$OJ-KEUVD5bWY(y&ImXUwkp1COT)J6f>Jepz*VGnnSR#JY$*HIgh!(m5FTj_$942r@WOXX|Dt=`G|a^(*bBc)proMT~&h)_*xWF`G~K=lUHt+O_Gb3coXNc3-?4{usLYGLpv?Faz2Zk#p{6XoPyTjvkU+T6#l?eUno2e%6U4nv6PcuRMHuV%Pd=o1}EiVOGp@(Ex}8lDN9A%-eLe?sjhK-1D8HcDQha-yfjd{0WEkIyu!NtRNicn6>)wsOX9_g6p6(>*>N!1GltNDJ9k1Pr$IepF)2bynuRFb;u;YD{m4-&!2Q`zrGmTjlrRV*wl7$6D*h!aR_p9d#ZMpOCoCwBnD!Ut0}vOv#!r=Sbt9(^aq$2&Ovez7B1(26UsD~oe!*8bGivv3@Qfp52swhkcNs#X{b>92=vCzxZ<#GSkR4F&PdMV8;^ujVKmcpHpjWh&Cc0Wlgkg#PV#>%zQ7{4-M^lbXn5Z(s<Qoh7JXLhgCDP44ps*XA81xG$n!iJb#Wm9Uyl0E)c$G<wu!Y=RWA=Ko<4I74enlsPM=8cT7>Ig2=tyH+KmHcI0CE2n{a@1u<6priTUHt20;EA62+%(d18|z<t1|d4=o4&SFF>ZFB0_kjgI27&l(YvJbvr4mzB{3tE4pS_rK|rYUGr19Q0FUj8PM5>=e5tA_tVq@Th{`BOhZ5{?(KbXXoqFIjkEk>GskiuZP5}KxJ9u{fvlg!Kt=0eg@*rkT^ck%BV)HOXgk&Vv(xz3YO9psBRItGkN7ZzhUa{sv9Q+{qen&^2neUcu$l7*G{WRZgmjj(zm449{cDYoO>lS9s@=>wFC{(IsTS_(Wev`yy>#S|W_Lsy;Wg>=cayFrJ+^rqgGt6O5_UDLPPO;@tH<c3<`gvwsKkC5cH)O2#D^&mh~!5|H@xM;D;8x`pqE;`=#c(vSy*HXh7R(I1*j65^B8B6$s*fqvgJl<(5-6V6;p|eumRa*KiiUGQZpKu=HvE#F7Xpbx@O+$58eeGw7W)i3d-a0QVPP(^U=H&CvpFUL%g6M(9`}wYK_Oc96H*tEd^zfGD%|_Njm7w>}q{q)<E`CofVLKdUdPLV)3x|%n&3}XI;U%$$GtzFvzkH*=E{%8VQObD~qHSu#V2s2xx@JP|!SnN<%eGwksp0q_Kzn!klxPH9n!~nRB8NJ|cd&nBZhzuh%;Y)=30@6&Axkf#0Dx$bUeT@27xjGx-TWAKb5S?PJ{`rGta}ouzRDqgUze@#^J*<5;m#s_Eb=B0$AHN24p%AOXXIv>#qY(9oboD=vA3j23is%Af*`Py60<o+q2_a;$>5|JMdxtlVWsC?{<{3YLK981RWfSFaf)#tgbJKTQp)mDRGQV$;#E9eLbH&2mQHIn16=2;&tRMnHaEOh_L)k<bT*$=V9$H=OP*{BGTZ`G$~J0$9xjw^48*R$I6Wr{BIe&<0@cMXa%1UypE;B;U?o#u63u5fvnsvdopTjPw6p1(dZIrpY49Q|YBX;sM!zj}f{n&pn6Iug@X+Q+i%O^|+m?qWS{vs7HJ=pEwm%4?2IsC+$%3k=E5ApSkOLoNtxQaW=#?0@_SOqx*oGL6lqxJro*K{Y%)il!McTrGD0TD$M-lM<GSs!2ZFn&I0?%p~1{x?hY}FyjSLs4`4)}<9vD&tuN!%G`^_ZNObP17V<`4Y4N|@fSOl1$!wv4{cUq$g1fpQ6u~JsgfKZnI&Nqe(rJINRD*ZI&GbCLmVvY_kiEAmki05(Ha-^HIUd-JSi2fmQnBouNOoRSF;BMfh0f?ky(4y!mBL8MrpW-p)lLiJ28zs97MVI0nSgAE7W5y0XRP;=+HV%9_X;8Qhb$s_wj8gv$rM<6x`HgT_XK-o+bohHk5}^UC0w{X*n1$ZR5|II*u%OJ9jwnF_S|x!mR<*ZSv$1D%FL_%o{{I_e9R*MhnTpPtyfxB8S4o3fG&7KI&^OtO=tI|i#T3OSvaUlSO>DaFf5ELM+~NjhkKNsp0NbXuR&+Oe-Ism5T@)<O!5P}x=S$8Vb(c*9qB$_=Zt6DIA6gyFE)1d`sZt-Q#tjMwNVYN6F!koA`z;#6w|;6RAMT-(%O0?#JrwmU&P7gO>PpK_2%&&U()vP2cl_;*}qlU<KxJswuvE^<A{Zq0)zzCUm~3tPAj9vOR^nr6Kxq$twJqub*<JSlSSxW7Bj-;`x;9pHP(73FkwuMh16awR5PHk5M^z#>nM(E<TP7k`Rr{WMPeno8_6~+w~{d)iVgl`TilrUOsg!+anQ_n@~n<oEnZe~-UcmPQeQuk#>0FKv%%y0`<eWILBPF8Qf2$DF@=j)dyp8;+49VF7sDE+M)=TE?H<QrwTR$c1y$I`$%b&((Lr^+S%F;V?VMb=gp}J;7(3GIQ8_Ijh;Q;4@gfB10{5P!A-!qfMZvFW_G#coS6$(n&uEItvlpp*-B!z%#Il7Lhp`dG*DShk9o{Kk#W{~<acp#TF<j@_EPK-zwTyu;<&I#WE0Nj*=Y)ncVK}#nI6tKa{Bb2QhQt@unEUybh~f@%`=(Y6WXwXPfw2}Jj!oVz+L+0=i{<w)v&Xp@$eIl-AUgrahR3RiyhOkWV6zj^rYmAYss07M#p%@0n}>h60#=m+05*ZK<P>(`>QJhNMdvQ1V%wm~KsZlvc_sI=mqW1B{n7sJqzGjzuBvjg(KLRtjlC9-_4|SG)26T|WMA1ySDtj*e29;<7*uihRryKoy;sCM8LgoG^;#x#qlG)LRQgF^%OQF8BkW58lZw8gp0-NtVBrWY!R9=>rDoEQFWk52ekPvg+-CRZXmqbrG>>O#6y67#{^vBLJjV>6%iRWAQIfrF<Rt|TOQol&d}0chq!9TMcn>Ae)R#SgcgZKlX_fTS<wwThX0(qN@pvQaT?1=p@+?<;R9@wo%10aqnyDv}csh&?ed+4w$KU3m&e7u>K3*#EqTH%cyo!$Y15e{&jl9M7un3fR!Q*_!BfO!?@0q7b$!3~K`8|cx)f}v+HTe7zr$cpW%PA;xWW?jtCG_x5^q_M4DO&Nt6qK#E$r2`WQ8Pgy4XGkgcNZPG%)xQQA<g8PkU!u2Vb?kBWAhlMk4Ze1<*reJDz&C`bx#D?IqNYptn6({w8H3(TprN}+YIO@Te;~xj!i3XiamP6gb*qGa?z#yR<@MJ<1gt7MJFpYT+`c5BB!HNmrq>U4=WMm+-V;}d0oBm`7FB&`SF$(TAZu5$PLP#)K=G0)hqdwz8TVXK|7?EBE2r{>96QpoVkd8fxf5cm!Hyu9*u}Sl5V?t{>hfPO5clUN_vBmzS0)Po4K?DBD=dW+F@`oRm|nztVoppAZ*_(*ubMIzbYFEHCZ&9?L(WALg)m!GIDjU$l@bXUaq<-Haev*i<QSUlq!AjOM0=UwGV9i#rc{(`yG1sbXB(<Pg4_Ko#Q!L8g1uDgs$s1sCi=&DEc+6s~0jx<QBp?6+2kVtf~Ms!f-8ST{CO06A9y+U3Ach>s+4k8;V%e`T%FQVXy@dF`BgjOmyE^FRwvTw$+|I(L6piJig|UPxwcDz=ro*I;laDYQEI)MT&1;^4Y`MPqxi#cF?LdiV3O6Tb}S$<rQPEAI-?)aza@5id5ufzv8nV9m1L`0&;Kdp*1w}%BA*vx1CEc*OY(ibNuHGlvCH&bGeRYfm_7xM?Y9t(DDhX1kW7~iWH*>gLz5w$sHl$QhXldJkz^{f1dA9p5dd;{;=>)7FnkB$ECcT7G(&^^MnHwPMQw8W7Y~t|5oZ`meh9o`X%3PPslu|2|hFEq>C^48o*b~T1uYgYkkePB9^k9k*6H@@BaWp(9cB"  # noqa: E501


def _load_scenes() -> dict[str, SceneEntry]:
    raw: dict[str, list[object]] = json.loads(zlib.decompress(base64.b85decode(_SCENES_PAYLOAD)))
    scenes: dict[str, SceneEntry] = {}
    for name, data in raw.items():
        code = data[0]
        if not isinstance(code, int):
            raise ValueError(f"Invalid scene code for {name}: {code!r}")
        param = data[1] if len(data) > 1 else ""
        scene_type = data[2] if len(data) > 2 else 2
        if not isinstance(scene_type, int):
            raise ValueError(f"Invalid scene_type for {name}: {scene_type!r}")
        scenes[name] = SceneEntry(code, param if isinstance(param, str) else str(param), scene_type)
    return scenes


SCENES = _load_scenes()


def get_scene_names() -> list[str]:
    return sorted(SCENES)
