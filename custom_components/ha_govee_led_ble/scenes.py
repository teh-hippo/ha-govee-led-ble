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


_SCENES_PAYLOAD = "c-pmETXW({lKv}>ewhb4q7YZH5$B<F=h(6lHg4mMeE=*9S%7GPEyKqC_sy)E#Km^cOpGIRd`xF5v-0|77XSNW`?k)LZT#cE{=5G3$B&=&|M`g@ZQ~t$VyI8%SsriklZMf0{`^7rV@e}>O<6$v$gkThv-eiy5n@t0Ap8e^F9#;|sQ-)Nj~!CVOb>ZH8g$_ktHv_d0-7B>L*Qv4zxuH<{$HfGqM+|tk=<QH79CV*=wE;R0QDwsd6rLvdM!{dp_(;hF8`zU+IKiBsP+3Deit^?YEkNlqc|P>q{gT_2UYMm*+3ixREB?Zh!VL>*kZR%)=WrkgVg&KNOZYWO5urIo9siM8v}k$e|ynW=tfVsXK%ck;yW8%^XCt1n5F6@^JqZ82=Esefop;%fM-}5YR&@l6B-5%vxRQg6loaH2wiOI(%?WBSys~6=QJ#6(M3HiX$HgsPEuqx%2IUviNu+<yGfq!ueRx4n5m<kW21@u$ZLhKeS7bKb5Px&ON82#R$|6MT66%$0D0)UTHM{?m|mK4yUDd@x)`otM3#BN$Ku5h4?a0CN}3oGGNi!INujJJ#V=adD4rA|rZ6_lh`x~Kh+?#o`j!e6AU>?R@C0@D@ONJx&Bpf=avrwZx78}ng__`OaDaBC6i3OSZ-sbL9j@b3l_;p>aTPH0P$e$vNm`{0+4*F-6vBF+3qzZf!qQ8^{L}NRe{-obs|qZV^-i9z3&n+glp<{g8BH?^-V^~=oSPh+%{&aih`LC#gJ<(j$P3}=*mt9#2MKn8K0Bia+CBuZsZ`4+$$FX<JkfNKOY&GKYhdPaUqb2fijduPG4zZfgrAWHLScuv7%TVb8j~3hwTf=Y(?<*a?W;^Dje0=p@Dwe0*xxR5Oc&!TNf$uk|1lqRYVh=EvUKPo8VR59EVVj|$R{5oPRE};=vd4ixK9el<ng>uMJ1s+yRFVp@*RM_1#*lQ=Ocv~c!kqOUs}qSlXq#H29~-|=dg6X&P$%dGB4dCFslLo633gXZ7eEv7aPe!WlR}iP0Seo;W)9e8L*6p&NU65L}d4&8PtBAW>q@Lx4WyE*0*)que?<CtM>@%2vjuE9@8~61rG~7^U_N250K}X1}mQYU}$R~3I-MmQhz6q4DnHN+p_sU-wT<u!oUGOhlXGizst+!smg3QnI$Sypp{rQ)ZU0b3uie53&}G!DV61z0Zf|5wjRHwRi+eY@&xS-rzIbek921(N`3|b+mTi0h_6W@flv4<Jh?twHchTx;%%G@{Ltk+z{Ym8M;k4fbh{Nf%hx{LI|Z%7@6z=UB5Y*I9#D856z_CwW8o&<=&Y!&vTV&;sgQ={Ke3o7|6ck`t&~UW5M7UDxyF?CE`6F&t06V>(m-kkv^I8BYIWGDwD~eC;{0l!#LE{U5DR&-XJD>p44ox&?zuolgL-7eqzEZ#6ue0DBS6&mB1b9!XSaS!1>C(SMM3yjhr&uug}-FQdXv4$xancsgau`hrTj!$AB07&_D>~9-N>m!JdA+GQn5p$h?4!-S5&8vh4U58oZ3Br03(OX;Bq*B_d0}z`qA>~$xoG^KO#r=AUmMUpE5*g#ohB9+kFLch(|Tc^;)0^llKx`I6jKP;=m|n*lLL^9F};nj4x72=UgM*`~%9k*2se1044HI=&+PZVDp|WXOnd%^ucy<e~TIGiQXn)BzhFx3%;Zn<zO7@v7jvsar^j3^c;5nOZ5MoJ{b2BBH5y{aPuP#@<3?*T@5{Xeg###Xn}D75*--}gm>b?^fb8GZ$)!6+yLss2hfb5t~9^q$pXQX2B3l9u?z=zT#g@^;Hej;jXdN7-i>k1>FP^?HvGL4IS>9YrJSygjgp^8(Y<OqTA@2+f{sZ#dGcA7ugi2dp&MF@`svAO8)K&q;JDStOxw#!wm+j=NV-N?rK|rTUE@=^(9tS%6=1L4*She&-@5kMtb~LEz+~?5p*X6t@h;BttL*~IpRh!eV|(-`MM=MlzRb|$UIhQ&fpNnCeYDlSp>3DdcCT=~*^)(ojo}r3Z_EZEv~}kL4TV^y7(ZInfh2I+7Qz)aLIX^HMM!5lhhgM)A6{#OY=ir|X6<g?ektiy3lG8ry{^G~X*V4^q|q4@BfKR&_I^6)?D9AUb4*?Ys5H!W72Wvj$LOx+6g3K%%YGTO<Iw;jLzhFGPsT_$7_z~Q6=jrTvs%4qliq7tMg`1(PWg)ER)^#w#wlyM%(mNXwH5L^Rry{qlM`JNN2tSmM~Z1p%hxT|?fFb#LxyyXyxHr&*TnSa7`hb0VJ9mg2K(zrW60mb{1*mMA_q|W7pWPK_c?U!K}(3qB54j|7YRB*AJ)z0p{(}SZ~3l(JkXn=8fN1`_t`@DOP!6z@X2Pg6d=zOvobwFxV)Jh&B4|tx=6!;A0l2(^Y|$ZRW#YYjF6JX9`p+Ro?&KuLetgni4-tKe8j7%QLoqA60(Z9;wCHxe*?EeamDfhv3-~UR?oz5`1|N|g=?Q`4oMswo$exy8)&VRpC{{=D~6-eRw|}~s)(Te`V0*&6@#P;3(^|B%5_4MR^0IlIn3$k%z}zDIqmIYe<P0HF*<cbGPinG^rL}ov(Rq8_FadVeY=<wi@d_XFojsSX;Fk{_N}d?`Sh-9vpc(e=)0tMyWh8-h%<U8qxae~%z*IXK??NlF+IE=CK!A-%D{J{3^++B-v8`hp!bjld5|9YngeqPGF~{3PR~5q?p70-n7w~)A%Q)p?CRw{#E*g%;BX80_(DQ0x5R7^bU=%lo<&6EugQ#aRDVStH?ogF<zli#OdGG!8GJ}%#gz0AOK@#q?60k1*2WEtiJxs6FpUzh1E6dd!V$W4hJ6E0!sw5m23i0DX&Eb2-ctkjG|6|1mx(}iJw$bhDeZD2?c)4r7dEP|z~o<Kc`7{AGkE-6n!sG~)=QJs?c*QOv&tlf+tBJHR=^31<5I79#Z(0vf5IoMQ1X%H%`u-m>1LAeq`h&D$7K)Ni^rim;)BXZbi=ifNLuz`ZqHH*&WEP_Tb-!T^Rgd>6g30e2VcDltk*xDncY1iPI0QtAs@hq{>ELxNu0h+*0cDkavqL9syc}Ce5b>|qyPErxr0{xkL{HX>gqO{2c@fa9FT-t+JQ7W94$QINtoVq^s)URZ4)FPOnN-XskPpz(DvzK#Vr>rm3Y#Nm2-jCB|*g^*~M2Xi;a4lZ@nvJo|Mhs0svY&8{wd=>_l0qV_6BvZeT(m1!!q?e^dL-1l3+4u>KNdBhOZo^)8tKOIOv5Rra1>&u{6=3dr5HIClwou8%fTh>2w$x;o;pQbb3qO^7(R+<XXc12(QzZLrpxg<e-n^Kg%0MgA|o7m-$8D@kR1BTxmp;0fu_tz`^d*kLc@cq1g?N<lzUkmQA7p(Qzdg@8D|OD}9fa(zM3>m9{JKV)7S@@-4su5NqImu-F>={{SwP3F5eUuPNjK%-v&e5H3TrGB>3tD#-OCvq|Rpgs#B21Z@|Y<peXjJc543(U(n*}jSGZlm5fy&)2my@x(;jC?!OtlSXcXe>9pp%^%+i3b972UcGp9bX~n(dZ@FO?HX039n0`61TpUE34@;bgvP~EDkj*oz|@8JAsL4rfnnlm7$!}xoxP`;+v@AxE9W`WtPw1mO>!bocpn8q+&}P<14X+pKb1qMOQb&LcR=|^<KQGtyjI*mHf6r1DDh{kHi=)HZaRPzQ3R4`U{Q-%OsUH?`R{qc&L#;p3aVCuDcx6FcHF0S2lB8SI8w1V=|D!9!_C|xsD2?+wB^pI&bGv;Q&HvS55_yT2+hL28WIYn-ed>fkNJ(U7#V|S>Q#%*EEMTaHE?Jcgbfo#q`;W<f(?$0wwTw!H0HiHSw(#Jv1+#NUd6WdNwGdAJBN6x}J#MQ6S)vQ-MadxHv)(SIUJCT~D__yrY5{fcsd@3ip4)lL{U+J20VlypD4gi{fo`RI%RV**tqw?lE;xT#LO^U)4%^laLb{&bhPQDgyqL9x&03z&!%<lo|5-E#a*Pr1o?*?Th?^YPg6HUpmuwlNxjJxY!)3^=Fdvk+)%Bk=t{4I5<^<djR1tK;L#m8!nG!srEPYCZjV=uP?vx5`n54Y>U9~cM61X1uYcA!g!xjzQd8lDqN(v2o)Rt>jBv4fzXRTvQTDgCVNK1XlVb~+EPoXO^3er&$h6q<S;nBv6Xwo0bYSx&|}<J=^t@xvL^al0eb4#Y(&v9nz&0$g@35HW`6b~?3WxJ^NuIKXP|-*FV*<V7TK_zcghWx>a+X?aF{(@qES6q(mY<Ik#h&o^ggE{<$L6KzuIr1O(xmfRveL|!nCrj2=Is$qFoFCGJn-kkDzAqiD{Z8y>Rx4X=GmJ@iLxlMO8Miz9-L-%5fxnrs8T$14VgvjqirK&=XF6e*9w|>Kt7GvdKyc=Pf}lIjU&w(ANb<;eWn|ErOoD0q1+d%RJTltF!yZWIM}*^sby1<P@%^Mfm;gv;eiJCFZcq5pj-lAJ@V^(}IfqIR^=qIV{`kl2x)5^%2xj5HI4LVc8bzF&u~-(nxLz`TNZubez*JyNF@_nZ^@Q+Kdw9$z`vr`ZWOHdDkKXa<ubPU$3EeVi`wAwq6aK>^EnNIMxuO!Ea!UsB8{?xipmiDjS~h_$6H->Fy;)rrvHEIc=%9xTR~2);zG8(>fj~RIS2WeCs}Br+aQ_zpmQD8`OG|dvR0Ns^nApMo3!)ZIf<_^s0!bU(q+2<suFT`mUs3eM%2{7?JfzI<4yav#;p85lu<AU()LaFxf7I6%cFQPtXeeqse9=zMCbcg%P)Vqp<oOl{uyNAac5CG+M{@B!#-28M`V!M5!^$)?cyDIel50Jf;9%Y5y<j`KsGKvgbGNSM=GR(7UH=&)sB}>cDEBPVmBDdq+$Qs#b%NcRFpNuW4Pi1d;-G5XLFrWSe?52CxstdOm0CNq3Wok)qMz*KMr)*4G_HbZmZrn_Dne156mtTL2e2Z&o+2K`OT7Jwu|Gs#Np%ibs6^W84G0`mm$Z8l<M;OUq@f<Xe<{_MrCL+T}GnXx5BkN-FYJXM9z8#l-7HbMm;F6037VD)O?g_{>L#SdBFSxkGzk4zxUVF|gS076Pm_#Mi&lvxPo&eYF!%am=v^-!>`8yrkuAx`6X-25J=Jsf9aV$tO0Fh&k~d&3UHxOaC(8u{_O3okO+MPM29Gwa04>J1xrK6K~_jmsn^v=uE6;Kzc)=kp}N}`uZ*3{y@kgsBu0$cBRX2`3&GI=1nP2@io8aTN6`SPRrv?`@jDOBlD>B"  # noqa: E501


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
