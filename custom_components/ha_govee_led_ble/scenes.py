"""H617A scene catalogue — generated from Govee API for H617A."""

import base64
import json
import zlib
from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True, slots=True)
class SceneBrightnessSpeed:
    """One brightness block's values for the shared scene Speed position."""

    block: int
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ScenePage:
    """One adjustable page and every field driven by the shared scene Speed position.

    ``page`` is the record index inside the scene body, not the entry's position in the
    catalogue config array. See ``scene_body.ksy`` for the complete config-block mapping.
    """

    page: int
    move_in: tuple[int, ...] = ()
    move_all: tuple[int, ...] = ()
    colour_speed: tuple[int, ...] = ()
    brightness_speeds: tuple[SceneBrightnessSpeed, ...] = ()

    @property
    def option_lists(self) -> tuple[tuple[int, ...], ...]:
        return (
            self.move_in,
            self.move_all,
            self.colour_speed,
            *(brightness.values for brightness in self.brightness_speeds),
        )


@dataclass(frozen=True, slots=True)
class SceneSpeed:
    """The vendor Speed slider for one scene: one shared position written across every page."""

    default_index: int
    pages: tuple[ScenePage, ...]

    @property
    def option_count(self) -> int:
        """Return the shared slider length, rejecting internally inconsistent catalogue data."""
        counts = {len(values) for page in self.pages for values in page.option_lists if values}
        if len(counts) != 1:
            raise ValueError(f"Scene Speed pages disagree on option count: {sorted(counts)}")
        count = counts.pop()
        if not 0 <= self.default_index < count:
            raise ValueError(f"Scene Speed default index {self.default_index} outside 0..{count - 1}")
        return count


@dataclass(frozen=True, slots=True)
class SceneEntry:
    code: int
    param: str = ""
    scene_type: int = 2  # multi-frame body prefix: 2 (default), 0 (simple), 1 (e.g. Halloween/Sweet)
    speed: SceneSpeed | None = None

    @property
    def is_simple(self) -> bool:
        return not self.param


_SCENES_PAYLOAD = "c-qZdSySTLxBn_uzuX6?+GGHdTXi0G1_(z{qGGppod>`WFi31bBiy>*{jRmA3<S0N)W7Olo#T<LJ*~Zl-x~OzZ`;@PX1R^N{rAsS^V_#(>z^imw2gM~i6%dpr<-VtpXgf0Xnv#ndrCukPUC>|!+y(+Q+Mx#Jwhx>M}+<0@72hnJ=*_H@y8uf8e2Ua)1yHbK5-gx>N`NQgXbE?m^fbkI4S!t(mP===sBU=U4#xD6=>*Re|>A}&7Vf|Cv5iTKkT1wbermF!}fo|(SGVJtqHqt>N-4a?H~Tr{5E;rq?-vpnh8f+Qnl<b_Sqker-8?og(LlXgWs7;)sZOmI2*hUe$t4kKZj!=E7B2X0~{CLc|>hj=UWon)lAr`F189=!jrJQo2LAb|Kl58E#t**y<Eq9&u!TA%`@!RXM3g;p3ry6e%NQ%06*2=z3|7-4}V;i*r)a*`DNIA2PXV(w-vwC@@G@rfZny5-<<0-kxZM1BLa5?f5Ba`LnE``xz6u%9tYM5ni%BD<p(*ZND~7M-?&SC8XV{%O>-Lem?jQPx@aXi&4@TKl4PliYe_oxgn|LUal8~MJf?ximRx82!B-|+l4$`q^wNcFcazO#f3{8b{6;!Tid?*ne%LdIPXl-FffV6kgD&BRrnI0K9@3(uprDi6fv+}ubtuyprAVvZS_^JWx0&3?8{58Yl(ckFdEu_&w8y2E?*JscPYy9921>b5Fp%73CND?qb77w2K1s&41f|^y=_4`56m^%hwv_J`B;IN93#a}b{vHS(xHvx{HA<|Nw8CJAkj&;<QPA(gD}Kn==jUj{4+#<pQlg|yY?hM4z!@S#mHOUS4@BWWJ$3-JVt637(I0~OLWR*FPF5?vn0<ON<Y>NFQny&Y%02ncr{1i%V76TE#QC~lsOfvYq#J{Eq$vfV;aZR#Ul_<#+(Ru1sgE=}cwXKJc_hp{4g4^$!DQ6Xr$_WaI{+=SYOJqrpus>j!7DOy4bp2~m$hg!S+1vP#%zjmJIhVPkF24QVe$mdq?Zljt1jw^b`83sB>_LSM|_mmn`Dhf4q5XYUXUN}Cdyo2T0o+=0@8vfGvSH<_G8cTQO1|a0!aE_9!I?fJT_gfJh}+S{AQU!aypB!Pu|Cjjy-$WV>Y{GH=B7D)2V&JjV4uw%;{W<aR;C`VI9q6<49%&z07N)L^#J@g!7c!X~lA___<#2B5Wjl)Z~v@n!qSoJ?;d$M-!MO|4{W%+2l=Jn~u(Ds7#>{Ze`w>DHP_-&jRbnr?*bYj9Tk4ieApP5qIES#3l=Ac5+2C(CqYY%VreuMVvAXI;X)8uHXZ}7me?=rm5D{YHc*P%G4&4&31P-Q|C9USgDsttn?Owc?UN|+V^w~prVIBA?_swV==-p4>WjYrWQoX8FBNBW|_3!2pEs3WJ+BDUI23qWA7PN1jc!E2t4k0nJ@g<jp({|gq!e~aMuR&C{mRbt$CW3u_RtiW=m<g0IWDJIP8!<aIyCYx`hV>QPS$7MT*5exz63EwDL|l&w8Bpg3*%qu#a>{AV_=$s^1Y_pft{)U{EXL3S%}^AXkspJ_B-bI$fSUM%!q^k#&~=2Nx009&d0J3+Z)2Z}l{wdoQCc_?=5INP0YW1aQcDJ#gg7y^BtqbVK@ez<^g~=2!NdrfUZC__h!;ES;ERhF<bOorEdzHA*o0@<uF~<kKHB>geJKy(ADv09qH(9(6i#?Y6ib)4;21HXtk=nZ>rofU$7|0d#z&>=obke3fR==4`%<R*!t=2n3e<7_RpLRcRG_H*DuI4O*cSk!(nbo-rrSm<Hy;4n1)a;I{KioW$Sv#GXN&oI~a;YeSIADFj>L6U*Rnhbav%l4`cb>DU$I?0-zN^-KCHRK`Y?8D=yN9VwzT9>BgsUx{Wx|NYQwfhvrF#*u16!;q5weP2>l;{i4<^XAmG0Wyz0wgy{=jqjch0U5rVeOmb`j%N=yKYLg^pmBd1V*r(1J<Ji{79cu*j=h+)Cnj@A7^|_{Z%a{SmPJJ)QXE+PgpY2N3|Kxa|D<BT*c-KkRunl6DO<%)@(>8(<2A?n7K38S;k;*=!-AhAMx0B8!*Te7_+^m@I`16m=I?-C6c-(UR)7t@LWdY4JW^}Hz1&Z7F|&l2>BaMZg_fQ6EnUqf>y)1taoEiz8t@*6o;>PBg+c8BRiS9MKwxMu4%%EeF7LiX&!Xf%qW``9pnVeYkINkm6G^1OF`)T>*V(5Wh}g$QUc9Q<fBp0;<Mf08uFzBBqqnq@wMLV{B(fll;(lZ}-o+cb&wwMI&|kuUd}j4jY_i{SRIB*`xU+Yl8G{=%J|2?>d`uDmhxiyr^I(k6qTHB|X=Rp+W5_$qjkbu<wN^Y>>F>SJyX{{ml+m>iAv2Ckx+g_P3v`E+)5U_W3K3;mhcQ$u1dtpv7L9>)$7b1%{M#vXVR<n0=I_N6%(iRt`DhB`_ok?P`j3R=|7r>*P_uNi&Yh?Q7~Wa5sscsZXp&k!CFTH~&R!sr{Sn<l(CNb>UF(Z<`pI<xHy7v%IUzZpSu@`+1x?&I57b8xDf`#AS*_YDsnE;7sStB1Df%ic6Bl_&pU@h=F|YY$S`PH0U6gLlwhIJK{I(62yh2kzk(<A=fpBhR)D8dN@oAs|&y{3+Lffu&`H~6ka>lKiPOy*i1@qNjX0<F+c;WaSHqy86<IxbpEbkpf3Zv-k{?4HucnPoVU^p6&QB<biL!`63!*%F)Z=V{3Y=fICqj5EFKj!o@qzZ-ydftF}X*ap|h~Bv;+VGOt@mndK2wU52q6nBedF1H~&1x6J(*F7`ylQw^gF>|LK91Vacmz76FcfCz?vZYE9gi-YFr_Rj&}e0CVn5~Bi-&y>8$2OKlX;@qBEn?kbd_$m>GPJa-zl!&%Vr{NYG9`EFyE1E+EDAOpu)HNG0#fGNT+WMd+^raDOOLb2`aec9bKl#k#3^NGv5uy6Yu&pTQ2TD#-Mg08SH*14ejn`1L4fb<hw~j!8L6caykg=oQs#+97#IA#9RTnr5D#Su^f%M4-V#MsP}U0%XJPVO{?m#Yy2%fd5phVzPzk>d~fmGH?5>`7}zc4wVju+mWIXrnATx5cPDA6q)GR=Fy=Jw$j;O}*Qs`brmN-&%bB}^%{W3M`p2)0k6)V~y%q@^41gJW(ORumTVzal0`Fp&jsAuccoeHk@1V+uSwOUu|AxOy9L{{V$~~~|L5ah)G=88sBh+X+SwEh|n3LR!jY%EKLclxy7%yFH3~bCWBj)%?lqd{Z5Q!%+e2k9H9B@UGQv9RJPyF~Dt<%D2?^309`{BrS<DuJr8u%Wu25vSd4tXM=u^`hICdIJYy>#VjeR|b(<14p)82H4#-0#gF#2den@mu4;j{}%^lmNY7rib}&2R_b?YvA0t2ApKb=YQze(D#rA#~?k9Ge*`mtntXkC~LG?Zg<ZUVTbJBt3Dv+%Taz_CFzI3^YCflz&KWYkhM9UItn_li<wG=aY)b*mcx^H7RUIZTN}fdBv#_~0;sB#>W-*2yVF$Qil;J;26NnsQ7guvt-AEu3G`WXiKenji^&SpAJG~Gi6uhgY)Wj5ix?-zlr+}F!ITZL@Us^^gwNm(ofu-JcN36(ieLzCA*SD&8r~i#!77rOAX{eTr_0T5@i^fTu#FM$(h_%iA@0=s&sLUX5oWoGvUHPh>9RGZJ9WuLpU+yCG`zg~5`A1qGGY<Cm}Jc0gjv}u%dtFR2s=J8j&mU&M~sW|xT@bO$wLv`<)14s`c+zy58$FH#Ir{5s>6&w8OCJwWwO}`>A?a4R>|=8nMLr&EJODmUND}D9EyOEOgeI&VItQOf6M#HRN}lJ4k_{(Bq{i4E|7&mIeG5yF&Dt^DD}uY3`FV0B1P3=lxvp!oW;`vV_K-=>Q*?SXytG=XJ9+`xSDP?@lhbYJhgP4ll3e*D{zy6_aX;4H$UURzv12|Ra|ZpYpb}GS0eMg1N{15+cRZeiY*z;JovJr1EzdSJ7CZbrD8ff%UD%)1_%a`)_{E<ELu*P*0*D51;bt1vIK=)i-STf7wP$=y76|k6y@iosDgD+rKsagJO8Q8W{c%6I+J!?YqePuNddHw9FjW_XE&;#WebjG#~n=z9Zf)XBMXozM9@z67j<7PINlQ|=U?2BY|`h+dbgaxkgoJ1&*|F|QM9SLj=-9)Iq&j#<-Alj#L!<@W?yM7`i`(vR|l>2^D+;YSwHj|b-rHdBY%!FdqpQ~9w}p4A=j#CVt3UMdRWVG!v1$wSrXU3mfOz_4~DKl7yLjvl-XRpDr$zzT1C+dUkQsGJV=F=dc$F+R`OU;19Ko<N~<$GryJEoWZNZS9Sq}MGGrB}fm^JX9oJ3!Eu^chn<BWK@1o5*P1&^~hfh{#k5_3ORc9N>m*Ed`q!uXB00a0U8j5o3s2`*8a?cidsu{eBmfKg}X`r|CY7ZEvv~LFtJF<F_QRo4~Y_jM!81ft_weUa?gaOx|k&b2cYkRF&NkbQ94YPfm{3zAmd2^2`(56C>6=}?qJCDoVWVe*uXU<_L54OG(1;XiS=$~U)u{boGWZH0yH$pQyQ@0>$*F%v;XSYBdla=!_x5UU<x=J_m*A-t7P4~?`M~1vNBEl&VlOA=wXp62wcUi3`!Lwsxq3A9Upzir%ZPjUTUa(*;Y|<yKmph`37cZlBbocglWX&EiHL+SILI667Pd=V|%p*l_7pK0z8Z}TWhvTjQuvl&og|9dkQa!XWNkn4blTv-TUBjy0>xse_Ub)_FYHg#bS-QB^uHDoiJ^&O@EOsf!smzgp0_+UH4t|EN$V-H>?}8_CFm<BGbJ7bjEh2jIYG_Dz7WBg4W12$}_~Au|$-pU^Z2Hg(1&^+a2AxOW8O!A&z=$rL@YX2t$0+8?t1U&9`g;9qy_o1R>q{`FUz_S~I#|zb%cq9vvi4%D<V9|KLZ7y%-{ZDp9Pk*(E5tu8Z$!gLEoTjU==T&h!;ZOw&v2MZX54&bOv1;=<VIX8dJG}3r>3G+lMOnZ%Zb*}CXTqH*E-U%ziiTZ`YJ`!QtEZiD{uqp0!2&EhS1@hsf}NZ{ZG<EM0LTVCLS@>#q(zKR2@$H=rudkuh%65JFs_Kx!M6YiQp<1A;!4g^v$B$oIgIok)m^&Y*^}3*U$s*S%^BS9)<}BhTsr>w?nG?%(jTbe?o7?bf)N4-!%3BQQ5%k5HmOqU#g|ey8e}ujKO{jek}C4Hwk5>72yYmiv-Kwy#3~U1ow1HXzfoet}QowiO%D69Sg*wYq}C6S6#&l{MBKg#AutjQ*szp8*N45cZ3b84j>%=Nr(~es#+7(u`aG}F?o66UPd#pxSDVQpuD&Ep&uezV<`ZJw?q%TR6=YoWRoq@>pUTq*PbNGV;z;(>1`d2M1X?ku9ik5SAfPoO+)f|!m5(k%~S1uS|I~grN|Qqr(PR1uZ^mmJu#Xinf(@U<T8ET@>^grVN%Gt2Y3q<>;_N72oo!BqZFntPu!l7({qun++O^fP1l=f6-~ArQfLTHmJgw{*Ert;<!yi}78G64xCyZFHW%23yDyKSo>i;bAGprbU6t|VS!|u5A(4+ShGK_-ay2qR!b<d6V5{D0RtKyfQ|!e1TIZ*6WEl!66YWHwXdN|o-OKGP<tOZlq=`sM%LF9+{xoR<4$9=Iz0~7Y1yhOar2V6lQr=#|0)m><-akbwV;$wvig7^^uhgC{ec3Iams{?L;fOLs3>o}dwRt5CGhH6hmzRY6{n{UOyecqWM3c>K8cn$O)AAru6xw|Wu^}p-cO5b!r7EKQ@(#V?bvrtCRrbA7F`X@<NCgf$YpT-19NzTvGNh2R993#}AJS!l?ncDew6~jvUR!LOH!zyxHPidpGwTrgpLKU`GwG|apWV3`#?=l5K*+xApwOuELv%D)!dER%((6NNX0%PZ3DQfHkbFdM#Ey?y0HE&*`sb7Mun#SC?nuWh&Yyln-wkO(x`Uklq#070`Dub#tIGP<hUvv&+LwnJf3}+WC&L7Mnrs(bKrl4FnV^6SN_ngW|4JQC<BXX=>zOm?QDJ01v-OqCl~`9MsSx*;1e0X4@9W-|rjI*BD~}-xf_6-wJJ4P%L*rbKKcr_p3~os<Kbc?Br(dD>iv`}2a#y~_@c&ydwLcQfFP}|*pKX>X<JGPv;JM`OJ)RGfU<>Z=N*VU>V_IKU(<)yes`1uEi@F1gny}6bOO+xa0^cnnmc>?i<d-GSc<CM13K{3$I=rHonX%qMt;`JeX9o9k6GEfTtJB>yz^9m^1!t)W@KlZI%Q5^*IrlcnrnfsfZGexF<C45^FUBqMaqg(`%h_!jZeTRDY)T62Js*uLu9r=Eb~q<@&r{-bE=Xa$^rLasoktvfO<>(?cVvy!dbR#d&zoWL??4)LiI$U8`bjEXR<fi#e>#`>1u71-7yI3Uhu1p)c4KnXMnnC+tQ$ys#)3Uo)ss1x70r9>c?zo?12ePxse@e(VjQnyW3B;P3cUw<v+CE6E3c=<QSVShKGRj2irr%~k(*?>rt#UB2#MfwHtI|qBOvxQ-;v4&xyjR~<Msza7D0oJQ;ExD_31bb#$|IutS84ApO0G;OK?uD_nGyrR$k2dp6U-0dUib^```Zq3c;X)"  # noqa: E501


def _load_speed(data: list[object]) -> SceneSpeed | None:
    if len(data) < 4:
        return None
    default_index, raw_pages = cast(tuple[int, list[list[object]]], data[3])
    pages = tuple(
        ScenePage(
            page=cast(int, entry[0]),
            move_in=tuple(cast(list[int], entry[1])),
            move_all=tuple(cast(list[int], entry[2])),
            colour_speed=tuple(cast(list[int], entry[3])) if len(entry) > 3 else (),
            brightness_speeds=tuple(
                SceneBrightnessSpeed(
                    block=cast(int, brightness[0]),
                    values=tuple(cast(list[int], brightness[1])),
                )
                for brightness in cast(list[list[object]], entry[4] if len(entry) > 4 else [])
            ),
        )
        for entry in raw_pages
    )
    speed = SceneSpeed(default_index=default_index, pages=pages)
    _ = speed.option_count
    return speed


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
        scenes[name] = SceneEntry(
            code,
            param if isinstance(param, str) else str(param),
            scene_type,
            _load_speed(data),
        )
    return scenes


SCENES = _load_scenes()


def get_scene_names() -> list[str]:
    return sorted(SCENES)
