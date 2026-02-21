"""H617A scene catalogue — generated from Govee API for H617A."""

import base64
import json
import zlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SceneEntry:
    code: int
    param: str = ""

    @property
    def is_simple(self) -> bool:
        return not self.param


_SCENES_PAYLOAD = "c$~FbTXW*d5&kQ#eaQo-YPcg(bsk1{)|QQYTjNw70E<BuAQrG?Naeq$dwOOhu)W@sRH))`V7sS#`ucUt|N6FlS#8p7^6l^csQ>d1{I*SY@TCD?X89)B;+JNl+xp`h-;X$t`8gLM3*w;eh}_xRvCo*r`H;yMelCU<_j&Mx<I9OS7nYAaJ`a2Fi(M1BX9LX+-q*m>Mt=RWbNOGSx8rc&+p*J|$2K2UX!xIhegpN!FPnTbCiU8&Udjz?Bs}@0_B?PUE2#DJ6+R1x8?`uh=_+m)f2j%X%|I2rPClfofXeW1F4H0xshICp=}M5)4oJOOf<#YB<s9Cz=dgVgNMpe3^wW<YA}@Zp)F*Ct<IQG&w$1i*WY=88!Q+D1Z%5AqXYayAP?505NFiQcL|87;qOxc&c02HpMvA;T9MfyD>y5cZ4_%wVF}Y9npo7770XqoJT4+CIey~Ye;Bgf@&fDiGo)u(&w4)XCC)T>-=vh|Za#8_oY1hd|+}p$Vfx4Q5=QH-+#oL$VGTD%t7N|KdqeF?~>@ct+ys2^R=u{;RD)~|cj8ardih591Dcw68FBT-M|G6-<NhvJ*NLX-sfBkPBcc)c>MY`Il`}OJ|@~sr<2#9{3bMU6kj_y~Q9Goq{<2H-Ahcr8QuU{E^Vls3GUL5uz7(bxT-_Zl@z!RaRRojfy)g&)aw<ek<-6W)E<BxClwR9t7xL-u#s)te6xQ57UWFhJ5G7rP#CR<_5<9(L#1$%gFqpJg*5Ug1bSsmU*8{Xo(CtS<J&`Ps8kOaTY$K4vd`#fE^d>-GCI~<O8?at$Xz1>MV`QC$$#q?IXqi`)5%KI#%unc8rOTKHxcL4e}$Z51CA1kcTFWe5g(bjGpzbfN2u_8n!eU;x$O3L(ADd`oVRgLwhBw3$r6DnvuthaNWEM;)DFj<1z<DABtDRLP#=RAC%pdLWYto=AmsBFC1?#`x0-}Y%)_cLAAUt=gC^^CL5h_9e_`dANzpH<?1h&+!xT*|x$L)$~D6<8x!{gpu;Bu9BoF$`A<eni4uV&DLu%OkK!fTeBtu2hM|c$(@Yfr@K8b`1JHlCxZfHRKU%xlV8lexc0c*!N%3YE#mke4@ROwCpVokWL4l`Bc9_z;;!^IpS+^$lVjZ3eU#eEuW-kPsujfP@C<^^6v=Hd5<<)2<3J=b{EeBzIO{=htJaW5F+BvR^`9&eW=^n$ibS;dT~jo<Sp}jC3_f2!^)r9f-1kCJ#ssf(Rz)p$BJANT6>Q_Ou5}un)z9%Gy_`jDR{*0ic@K`MP4MEvss!fo=70p@N_T0T#pz!3*p{Kfr5wi*iKjxan>wkeU?{%sPD(FQULC5|5OTidtZry@Uahtot_GR%8S)He^GJM$GC|KE@E5ziHiXUi#_9?N|1W7TZeeK0~%Y$4v%Bb_M<>kopyG~SGY6o^d0btD`iMIlD~HzK`(u42mIt!<(F^Dkv+%`xd<i#!Ax=WIKxhl#aq%VTGJ<2D*_OfY$K*{ycLDbAj^0ru*))4IBa@j8J}m0&OJxE*&CE`qmd150ZQcW&|xW!Nt@SvF&(dR(g)kc%_U~6Pi>9R7J3xj3%=wS<zO7{i?Bn6xV--@dWp{dEBe2t55~PhM-EjMX?~<Z9th3v)zF*fn^hU~7W4#rUN1nRt71WVq=Oc$dz`fg7;k%$RNud&n=86zRHdu`CSCJWxlq?DbUDyD$LF;_IPa&a0FJHzfQg0xO1$gaqH2X@vP<&K*>;XafGp9H;I_rFFoC3>#X!aBaYcsz?|M9JfIh}*U(j~SnzPry)@rL%5F<Du=#RuOg68JFp`oy&7o&TdyATR)$Ht~D?$7{}A2HHd?%_K2dbiIt#<t<jRjYP2>pYe8T&Gxc;O8|sm-n)f%bML0Yebi<FJ4WOs<hZ`k_5~#ej-%WusYQqAFS@<tD0NXI3N$_Y1m2bh7cL1C?G%|A>Hs=3@_|B=MtgR>P3h3pUYxG%@+E_GZq~alJf+|jL9P3Zu8}q<aev`{bEYU2b+z<4znFACN(49G#alT2tr5#>6)8XfAA{lps_W|v1XHumm~(e%v<wXo+E-M0a1ctKu6~Xt2OR#Hqg6<Z4#5m${dYdOmxtL?ThtoS@Z0l>a396@{4PAmYocHk2Zop?ye1pP1oxMK^@CN+?s2zX`ClZDiuY2{5t-SM#3M&eUj$>QyQ*m@_iX0C5<!e7v`MnyzvQ5&zuu$c!((BY=X0Sy<YDq;6~{BA}WU8f!pOckH0}|AEtm<bNYnuN4G0H=Tvh@;_&EpAJTZC(MtPyym~qlI4f+GVmhdb7!YqD(BMijNV=$C?Yn0gEIe%SiaVYmhb0}K+E8)EryXuO-=y2!a;!qP|JP<#tkPxmFGuDe4wrz}Y~YhKtKJn5h77wf5KRqcrP^3iG3jbZjyzthhBKw@90o}!d&vroBEh^UCajM=M`{C;VQmHD7!K(c{<dzy)WX;^12pD=!#Fq(D=XYYaCv_)^diyNtq;FU(#>xEG^V!S$F`qZ${-iYAnyNnnAas2M#CcCWaOGYHhgNZr?A_jQ$K><mmk6O_w=Fy)p4s-h3W;|P><<m<Zvrc9W?%gkE~GgvDU>gpStOKyxA#x<DiF&0JN73K<^Iqg21?tS}3TcT9mYBDFp`zOMTZjD$GC?#1Ti$!1m#<&I0SvBw&UrZ;z0KZk4<24H(hiIBcE-=+k&LP0lL!k*&F^1KsB<9sU>nxq0c~WCva9Z`(5y)YYw?3`*MS!4M4Dx8+^PpTp5I4Bn|QgYW=51JbrY^1-Sg?NaD$d@8haI(ZwRPBorLt^6Z__D6z>dAdu^bOJZ(9l1TMR6thtMH{eL?X&`Jp`Prhp473Pglspopv3^{vU@+d^J0N&&k$JD`SRs>wM(bK(37@(O|cKQ@gT_872UN&0Ov>R3WSI%_dFA2SRLY{RTo5=SB}HvVStLY>b+NH-0b&^G#`gsI}U!xVOd#rr6rXyjkpcy!Uv>7SC(<}!A^6LBx{m{b0#4)kmN^EVI;Y7u0&Yd<NWl5B>;Dg9{c^HI2c4QAV+cpA2`(&fQbXMfeGqJ_t^$!JliFk70lssvsSNvzUO%_rT%WuQ$xE%5A4H;gPKf28W?FxNM)N@TaToW=MR_{NxFTZm0z>oJl(DnW&d^{yPzD|Tb1oP&P!_T7YUjsEW8ka9kBWm>Ev8#CWWVTH{PY%CbAYqTHNYV?J*{c$U84)%$^@=b~dTmtycyE!qnJCEwLgszDe6~yDirf#c}<c=8JqYds&b`tTQ(wYM!(@Oz=qT*Y7sDjd{;Bz(O4cy?IY3b<F<nypq!nXyCE>`kpoJ=4*iV_ph(-^7{!9^CHcZ&AY}39$xB>fS9`zx#um0HB5x)uBRF}&ai58AcP8}sE<Pl6P~LB>2kXQsqV{rsc-?3+EXAo*859>`iQ}sV#fR!@wEi5AJVYiH1y-}*EEML^x})IbjfEl#pKbC)vd0p1&ZKkA!k@@FUh4H-?pkZN><56BvkquUF_PMe3rlH8(PM$=QPg`bh%L*+708;Oxnw<BF0bY0ZLpDTp*}W2HDS-R90+|+BXGhKp_eR1;$W(J~er@cw<Iy59@0+g~uB?L^T^&C-xFm4NujODTr_ppkgQHO;3h{Qu_;fOYo_oH_zU1Ijc$pfMW*Z#3_Ej)gCE^wdE$`ax0+nJ(_2@V4}_G`4DV$d$M6WsWtgZsIuE^G>v~8W2ptC_hDfCvn`wnJ5)Bsm4}Ru7~)eU8_Klzto%dU=oK>$B@IenuPJXEE!<LN<R1wRhwL$kvE@imDVv6R%t;`?!f}_-;yl0RW<H=7?nHE}k`Gm`^V^STbQ@DN_aD+IxDGV^&uLhBjv5%3`z>^uG=JIB6(yL;$iti-R>BoIL_6W;At6P5)gy$Keqx$dNl(r`F^y1Tc(O>wTPkb~ERpFWE#Np^<B`)N2ZOKF<3KzcFn^z%{CNM{Jls8cv?9h!C0tfjH8xiP&tc$eIICf^-0T&h5-xe%&v>LCRF!@ATqoU5bCTXuAX`nXddPy$FF`icqBe~$xl3`5<C4@Oc&7!Yy`=23mGLEC@6shq(XupxIvOR#vbZifv~a;W!e!0$lCkeE!LaL|HmZ37W5XmFQ)z3II7zJ!J>BvEL(Y0O8&-BJB?z(k6|HyponuDnla1MQo+PGAH|1u#VFHI0LAi!f{wjM$<NlX)g`%UH3|I7bli2Mj#p&rs`)(xzTe$6G9Ik6s6F0jzkvQF)LI?BoX1BrZ2eoOnRIN%srEf;OUGNU;Wk|1!c=jv$masj9vOwQc^vh4_L61gk-?MJJdj7l3Z<W3m^NjTdCB10?<L#WRfN<?*j8+&N4F_}j(+~pOchc_7!XEfs<&;?;r~#qbY#-Z`6;dC_kCCVIgG!A|aau%G?DL+!EKR=97^$@XFX`p-)H$-}7w2pG{CDWR(?!~DJk3mCbxsFgGT7cFz^!XFD0yYlCjK?8r*|hx;10q#le<w1mq`EvVGx#+sr>Vhl(2ZSi!K=nowYM@#SvCoZ{XZE%%A`cMzc16gzk&o+teTd+iG8(YMy`_o<Q@^)AUgvfZpwnPil~mnlCeavErMTe9o};)81`rPS~n7iV3U8TfXC~$}7fxKc2Ds<%HSY3s#Yr|BBDLcbVN>F_3%h46UJ&rx(og{ccVWtx11JbNYt_TyQVY!?ccGiAdyXMz8l5ynHrEIJhG~jbb#hVdT+#w7x^6iO*x)M}D&iKIS`?XZW~#s214CBF~lfxE^=1q6|4YO&VVzpy{wXwp$_VUz0{=VeDkjU-In_jLpNE<TLY1w)m2-0er=*rQ~V8*4KP1W+}@VdD3bB{tw@uu4e"  # noqa: E501


def _load_scenes() -> dict[str, SceneEntry]:
    raw: dict[str, list[object]] = json.loads(zlib.decompress(base64.b85decode(_SCENES_PAYLOAD)))
    scenes: dict[str, SceneEntry] = {}
    for name, data in raw.items():
        code = data[0]
        if not isinstance(code, int):
            raise ValueError(f"Invalid scene code for {name}: {code!r}")
        param = data[1] if len(data) > 1 else ""
        scenes[name] = SceneEntry(code, param if isinstance(param, str) else str(param))
    return scenes


SCENES = _load_scenes()


def get_scene_names() -> list[str]:
    return sorted(SCENES)
