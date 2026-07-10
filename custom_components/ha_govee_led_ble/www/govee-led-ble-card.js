var u=globalThis,h=u.ShadowRoot&&(u.ShadyCSS===void 0||u.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,l=Symbol(),z0=new WeakMap;class f{constructor(B,L,z){if(this._$cssResult$=!0,z!==l)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=B,this.t=L}get styleSheet(){let B=this.i,L=this.t;if(h&&B===void 0){let z=L!==void 0&&L.length===1;z&&(B=z0.get(L)),B===void 0&&((this.i=B=new CSSStyleSheet).replaceSync(this.cssText),z&&z0.set(L,B))}return B}toString(){return this.cssText}}var u0=(B)=>new f(typeof B=="string"?B:B+"",void 0,l),b=(B,...L)=>{let z=B.length===1?B[0]:L.reduce((J,Z,Q)=>J+((Y)=>{if(Y._$cssResult$===!0)return Y.cssText;if(typeof Y=="number")return Y;throw Error("Value passed to 'css' function must be a 'css' function result: "+Y+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(Z)+B[Q+1],B[0]);return new f(z,B,l)},S0=(B,L)=>{if(h)B.adoptedStyleSheets=L.map((z)=>z instanceof CSSStyleSheet?z:z.styleSheet);else for(let z of L){let J=document.createElement("style"),Z=u.litNonce;Z!==void 0&&J.setAttribute("nonce",Z),J.textContent=z.cssText,B.appendChild(J)}},J0=h?(B)=>B:(B)=>B instanceof CSSStyleSheet?((L)=>{let z="";for(let J of L.cssRules)z+=J.cssText;return u0(z)})(B):B,{is:b0,defineProperty:v0,getOwnPropertyDescriptor:m0,getOwnPropertyNames:g0,getOwnPropertySymbols:p0,getPrototypeOf:h0}=Object,v=globalThis,Z0=v.trustedTypes,l0=Z0?Z0.emptyScript:"",f0=v.reactiveElementPolyfillSupport,d=(B,L)=>B,p={toAttribute(B,L){switch(L){case Boolean:B=B?l0:null;break;case Object:case Array:B=B==null?B:JSON.stringify(B)}return B},fromAttribute(B,L){let z=B;switch(L){case Boolean:z=B!==null;break;case Number:z=B===null?null:Number(B);break;case Object:case Array:try{z=JSON.parse(B)}catch(J){z=null}}return z}},W0=(B,L)=>!b0(B,L),Q0={attribute:!0,type:String,converter:p,reflect:!1,useDefault:!1,hasChanged:W0};Symbol.metadata??=Symbol("metadata"),v.litPropertyMetadata??=new WeakMap;class w extends HTMLElement{static addInitializer(B){this.o(),(this.l??=[]).push(B)}static get observedAttributes(){return this.finalize(),this.u&&[...this.u.keys()]}static createProperty(B,L=Q0){if(L.state&&(L.attribute=!1),this.o(),this.prototype.hasOwnProperty(B)&&((L=Object.create(L)).wrapped=!0),this.elementProperties.set(B,L),!L.noAccessor){let z=Symbol(),J=this.getPropertyDescriptor(B,z,L);J!==void 0&&v0(this.prototype,B,J)}}static getPropertyDescriptor(B,L,z){let{get:J,set:Z}=m0(this.prototype,B)??{get(){return this[L]},set(Q){this[L]=Q}};return{get:J,set(Q){let Y=J?.call(this);Z?.call(this,Q),this.requestUpdate(B,Y,z)},configurable:!0,enumerable:!0}}static getPropertyOptions(B){return this.elementProperties.get(B)??Q0}static o(){if(this.hasOwnProperty(d("elementProperties")))return;let B=h0(this);B.finalize(),B.l!==void 0&&(this.l=[...B.l]),this.elementProperties=new Map(B.elementProperties)}static finalize(){if(this.hasOwnProperty(d("finalized")))return;if(this.finalized=!0,this.o(),this.hasOwnProperty(d("properties"))){let L=this.properties,z=[...g0(L),...p0(L)];for(let J of z)this.createProperty(J,L[J])}let B=this[Symbol.metadata];if(B!==null){let L=litPropertyMetadata.get(B);if(L!==void 0)for(let[z,J]of L)this.elementProperties.set(z,J)}this.u=new Map;for(let[L,z]of this.elementProperties){let J=this.p(L,z);J!==void 0&&this.u.set(J,L)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(B){let L=[];if(Array.isArray(B)){let z=new Set(B.flat(1/0).reverse());for(let J of z)L.unshift(J0(J))}else B!==void 0&&L.push(J0(B));return L}static p(B,L){let z=L.attribute;return z===!1?void 0:typeof z=="string"?z:typeof B=="string"?B.toLowerCase():void 0}constructor(){super(),this.v=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this.m=null,this._()}_(){this.S=new Promise((B)=>this.enableUpdating=B),this._$AL=new Map,this.$(),this.requestUpdate(),this.constructor.l?.forEach((B)=>B(this))}addController(B){(this.P??=new Set).add(B),this.renderRoot!==void 0&&this.isConnected&&B.hostConnected?.()}removeController(B){this.P?.delete(B)}$(){let B=new Map,L=this.constructor.elementProperties;for(let z of L.keys())this.hasOwnProperty(z)&&(B.set(z,this[z]),delete this[z]);B.size>0&&(this.v=B)}createRenderRoot(){let B=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return S0(B,this.constructor.elementStyles),B}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this.P?.forEach((B)=>B.hostConnected?.())}enableUpdating(B){}disconnectedCallback(){this.P?.forEach((B)=>B.hostDisconnected?.())}attributeChangedCallback(B,L,z){this._$AK(B,z)}C(B,L){let z=this.constructor.elementProperties.get(B),J=this.constructor.p(B,z);if(J!==void 0&&z.reflect===!0){let Z=(z.converter?.toAttribute!==void 0?z.converter:p).toAttribute(L,z.type);this.m=B,Z==null?this.removeAttribute(J):this.setAttribute(J,Z),this.m=null}}_$AK(B,L){let z=this.constructor,J=z.u.get(B);if(J!==void 0&&this.m!==J){let Z=z.getPropertyOptions(J),Q=typeof Z.converter=="function"?{fromAttribute:Z.converter}:Z.converter?.fromAttribute!==void 0?Z.converter:p;this.m=J;let Y=Q.fromAttribute(L,Z.type);this[J]=Y??this.T?.get(J)??Y,this.m=null}}requestUpdate(B,L,z,J=!1,Z){if(B!==void 0){let Q=this.constructor;if(J===!1&&(Z=this[B]),z??=Q.getPropertyOptions(B),!((z.hasChanged??W0)(Z,L)||z.useDefault&&z.reflect&&Z===this.T?.get(B)&&!this.hasAttribute(Q.p(B,z))))return;this.M(B,L,z)}this.isUpdatePending===!1&&(this.S=this.k())}M(B,L,{useDefault:z,reflect:J,wrapped:Z},Q){z&&!(this.T??=new Map).has(B)&&(this.T.set(B,Q??L??this[B]),Z!==!0||Q!==void 0)||(this._$AL.has(B)||(this.hasUpdated||z||(L=void 0),this._$AL.set(B,L)),J===!0&&this.m!==B&&(this.A??=new Set).add(B))}async k(){this.isUpdatePending=!0;try{await this.S}catch(L){Promise.reject(L)}let B=this.scheduleUpdate();return B!=null&&await B,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this.v){for(let[J,Z]of this.v)this[J]=Z;this.v=void 0}let z=this.constructor.elementProperties;if(z.size>0)for(let[J,Z]of z){let{wrapped:Q}=Z,Y=this[J];Q!==!0||this._$AL.has(J)||Y===void 0||this.M(J,void 0,Z,Y)}}let B=!1,L=this._$AL;try{B=this.shouldUpdate(L),B?(this.willUpdate(L),this.P?.forEach((z)=>z.hostUpdate?.()),this.update(L)):this.U()}catch(z){throw B=!1,this.U(),z}B&&this._$AE(L)}willUpdate(B){}_$AE(B){this.P?.forEach((L)=>L.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(B)),this.updated(B)}U(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this.S}shouldUpdate(B){return!0}update(B){this.A&&=this.A.forEach((L)=>this.C(L,this[L])),this.U()}updated(B){}firstUpdated(B){}}w.elementStyles=[],w.shadowRootOptions={mode:"open"},w[d("elementProperties")]=new Map,w[d("finalized")]=new Map,f0?.({ReactiveElement:w}),(v.reactiveElementVersions??=[]).push("2.1.2");var n=globalThis,Y0=(B)=>B,S=n.trustedTypes,F0=S?S.createPolicy("lit-html",{createHTML:(B)=>B}):void 0,$0="$lit$",R=`lit$${Math.random().toFixed(9).slice(2)}$`,C0="?"+R,n0=`<${C0}>`,_=document,O=()=>_.createComment(""),k=(B)=>B===null||typeof B!="object"&&typeof B!="function",a=Array.isArray,a0=(B)=>a(B)||typeof B?.[Symbol.iterator]=="function",g=`[ 	
\f\r]`,M=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,V0=/-->/g,q0=/>/g,X=RegExp(`>|${g}(?:([^\\s"'>=/]+)(${g}*=${g}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),H0=/'/g,j0=/"/g,I0=/^(?:script|style|textarea|title)$/i,o=(B)=>(L,...z)=>({_$litType$:B,strings:L,values:z}),D=o(1),L8=o(2),z8=o(3),K=Symbol.for("lit-noChange"),H=Symbol.for("lit-nothing"),D0=new WeakMap,G=_.createTreeWalker(_,129);function P0(B,L){if(!a(B)||!B.hasOwnProperty("raw"))throw Error("invalid template strings array");return F0!==void 0?F0.createHTML(L):L}var o0=(B,L)=>{let z=B.length-1,J=[],Z,Q=L===2?"<svg>":L===3?"<math>":"",Y=M;for(let F=0;F<z;F++){let q=B[F],A,V,j=-1,$=0;for(;$<q.length&&(Y.lastIndex=$,V=Y.exec(q),V!==null);)$=Y.lastIndex,Y===M?V[1]==="!--"?Y=V0:V[1]!==void 0?Y=q0:V[2]!==void 0?(I0.test(V[2])&&(Z=RegExp("</"+V[2],"g")),Y=X):V[3]!==void 0&&(Y=X):Y===X?V[0]===">"?(Y=Z??M,j=-1):V[1]===void 0?j=-2:(j=Y.lastIndex-V[2].length,A=V[1],Y=V[3]===void 0?X:V[3]==='"'?j0:H0):Y===j0||Y===H0?Y=X:Y===V0||Y===q0?Y=M:(Y=X,Z=void 0);let I=Y===X&&B[F+1].startsWith("/>")?" ":"";Q+=Y===M?q+n0:j>=0?(J.push(A),q.slice(0,j)+$0+q.slice(j)+R+I):q+R+(j===-2?F:I)}return[P0(B,Q+(B[z]||"<?>")+(L===2?"</svg>":L===3?"</math>":"")),J]};class E{constructor({strings:B,_$litType$:L},z){let J;this.parts=[];let Z=0,Q=0,Y=B.length-1,F=this.parts,[q,A]=o0(B,L);if(this.el=E.createElement(q,z),G.currentNode=this.el.content,L===2||L===3){let V=this.el.content.firstChild;V.replaceWith(...V.childNodes)}for(;(J=G.nextNode())!==null&&F.length<Y;){if(J.nodeType===1){if(J.hasAttributes())for(let V of J.getAttributeNames())if(V.endsWith($0)){let j=A[Q++],$=J.getAttribute(V).split(R),I=/([.?@])?(.*)/.exec(j);F.push({type:1,index:Z,name:I[2],strings:$,ctor:I[1]==="."?A0:I[1]==="?"?X0:I[1]==="@"?w0:N}),J.removeAttribute(V)}else V.startsWith(R)&&(F.push({type:6,index:Z}),J.removeAttribute(V));if(I0.test(J.tagName)){let V=J.textContent.split(R),j=V.length-1;if(j>0){J.textContent=S?S.emptyScript:"";for(let $=0;$<j;$++)J.append(V[$],O()),G.nextNode(),F.push({type:2,index:++Z});J.append(V[j],O())}}}else if(J.nodeType===8)if(J.data===C0)F.push({type:2,index:Z});else{let V=-1;for(;(V=J.data.indexOf(R,V+1))!==-1;)F.push({type:7,index:Z}),V+=R.length-1}Z++}}static createElement(B,L){let z=_.createElement("template");return z.innerHTML=B,z}}function U(B,L,z=B,J){if(L===K)return L;let Z=J!==void 0?z.N?.[J]:z.O,Q=k(L)?void 0:L._$litDirective$;return Z?.constructor!==Q&&(Z?._$AO?.(!1),Q===void 0?Z=void 0:(Z=new Q(B),Z._$AT(B,z,J)),J!==void 0?(z.N??=[])[J]=Z:z.O=Z),Z!==void 0&&(L=U(B,Z._$AS(B,L.values),Z,J)),L}class R0{constructor(B,L){this._$AV=[],this._$AN=void 0,this._$AD=B,this._$AM=L}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}R(B){let{el:{content:L},parts:z}=this._$AD,J=(B?.creationScope??_).importNode(L,!0);G.currentNode=J;let Z=G.nextNode(),Q=0,Y=0,F=z[0];for(;F!==void 0;){if(Q===F.index){let q;F.type===2?q=new y(Z,Z.nextSibling,this,B):F.type===1?q=new F.ctor(Z,F.name,F.strings,this,B):F.type===6&&(q=new G0(Z,this,B)),this._$AV.push(q),F=z[++Y]}Q!==F?.index&&(Z=G.nextNode(),Q++)}return G.currentNode=_,J}V(B){let L=0;for(let z of this._$AV)z!==void 0&&(z.strings!==void 0?(z._$AI(B,z,L),L+=z.strings.length-2):z._$AI(B[L])),L++}}class y{get _$AU(){return this._$AM?._$AU??this.D}constructor(B,L,z,J){this.type=2,this._$AH=H,this._$AN=void 0,this._$AA=B,this._$AB=L,this._$AM=z,this.options=J,this.D=J?.isConnected??!0}get parentNode(){let B=this._$AA.parentNode,L=this._$AM;return L!==void 0&&B?.nodeType===11&&(B=L.parentNode),B}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(B,L=this){B=U(this,B,L),k(B)?B===H||B==null||B===""?(this._$AH!==H&&this._$AR(),this._$AH=H):B!==this._$AH&&B!==K&&this.L(B):B._$litType$!==void 0?this.j(B):B.nodeType!==void 0?this.I(B):a0(B)?this.H(B):this.L(B)}B(B){return this._$AA.parentNode.insertBefore(B,this._$AB)}I(B){this._$AH!==B&&(this._$AR(),this._$AH=this.B(B))}L(B){this._$AH!==H&&k(this._$AH)?this._$AA.nextSibling.data=B:this.I(_.createTextNode(B)),this._$AH=B}j(B){let{values:L,_$litType$:z}=B,J=typeof z=="number"?this._$AC(B):(z.el===void 0&&(z.el=E.createElement(P0(z.h,z.h[0]),this.options)),z);if(this._$AH?._$AD===J)this._$AH.V(L);else{let Z=new R0(J,this),Q=Z.R(this.options);Z.V(L),this.I(Q),this._$AH=Z}}_$AC(B){let L=D0.get(B.strings);return L===void 0&&D0.set(B.strings,L=new E(B)),L}H(B){a(this._$AH)||(this._$AH=[],this._$AR());let L=this._$AH,z,J=0;for(let Z of B)J===L.length?L.push(z=new y(this.B(O()),this.B(O()),this,this.options)):z=L[J],z._$AI(Z),J++;J<L.length&&(this._$AR(z&&z._$AB.nextSibling,J),L.length=J)}_$AR(B=this._$AA.nextSibling,L){for(this._$AP?.(!1,!0,L);B!==this._$AB;){let z=Y0(B).nextSibling;Y0(B).remove(),B=z}}setConnected(B){this._$AM===void 0&&(this.D=B,this._$AP?.(B))}}class N{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(B,L,z,J,Z){this.type=1,this._$AH=H,this._$AN=void 0,this.element=B,this.name=L,this._$AM=J,this.options=Z,z.length>2||z[0]!==""||z[1]!==""?(this._$AH=Array(z.length-1).fill(new String),this.strings=z):this._$AH=H}_$AI(B,L=this,z,J){let Z=this.strings,Q=!1;if(Z===void 0)B=U(this,B,L,0),Q=!k(B)||B!==this._$AH&&B!==K,Q&&(this._$AH=B);else{let Y=B,F,q;for(B=Z[0],F=0;F<Z.length-1;F++)q=U(this,Y[z+F],L,F),q===K&&(q=this._$AH[F]),Q||=!k(q)||q!==this._$AH[F],q===H?B=H:B!==H&&(B+=(q??"")+Z[F+1]),this._$AH[F]=q}Q&&!J&&this.W(B)}W(B){B===H?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,B??"")}}class A0 extends N{constructor(){super(...arguments),this.type=3}W(B){this.element[this.name]=B===H?void 0:B}}class X0 extends N{constructor(){super(...arguments),this.type=4}W(B){this.element.toggleAttribute(this.name,!!B&&B!==H)}}class w0 extends N{constructor(B,L,z,J,Z){super(B,L,z,J,Z),this.type=5}_$AI(B,L=this){if((B=U(this,B,L,0)??H)===K)return;let z=this._$AH,J=B===H&&z!==H||B.capture!==z.capture||B.once!==z.once||B.passive!==z.passive,Z=B!==H&&(z===H||J);J&&this.element.removeEventListener(this.name,this,z),Z&&this.element.addEventListener(this.name,this,B),this._$AH=B}handleEvent(B){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,B):this._$AH.handleEvent(B)}}class G0{constructor(B,L,z){this.element=B,this.type=6,this._$AN=void 0,this._$AM=L,this.options=z}get _$AU(){return this._$AM._$AU}_$AI(B){U(this,B)}}var c0=n.litHtmlPolyfillSupport;c0?.(E,y),(n.litHtmlVersions??=[]).push("3.3.3");var i0=(B,L,z)=>{let J=z?.renderBefore??L,Z=J._$litPart$;if(Z===void 0){let Q=z?.renderBefore??null;J._$litPart$=Z=new y(L.insertBefore(O(),Q),Q,void 0,z??{})}return Z._$AI(B),Z},c=globalThis;class P extends w{constructor(){super(...arguments),this.renderOptions={host:this},this.rt=void 0}createRenderRoot(){let B=super.createRenderRoot();return this.renderOptions.renderBefore??=B.firstChild,B}update(B){let L=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(B),this.rt=i0(L,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this.rt?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this.rt?.setConnected(!1)}render(){return K}}P._$litElement$=!0,P.finalized=!0,c.litElementHydrateSupport?.({LitElement:P});var r0=c.litElementPolyfillSupport;r0?.({LitElement:P});(c.litElementVersions??=[]).push("4.2.2");var _0=b`
    ha-card {
      overflow: hidden;
    }
    .body {
      display: flex;
      flex-direction: column;
      gap: 20px;
      padding: 16px;
    }
    .notice {
      padding: 16px;
      color: var(--secondary-text-color);
    }
    section {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .heading {
      justify-content: space-between;
    }
    .label {
      font-weight: 600;
      color: var(--primary-text-color);
    }
    .hint {
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    /* Painter strip */
    .strip {
      display: grid;
      gap: 3px;
      padding: 4px;
      border-radius: var(--ha-card-border-radius, 12px);
      background: var(--divider-color);
      touch-action: none;
      outline: none;
    }
    .strip:focus-visible {
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    .cell {
      position: relative;
      aspect-ratio: 1 / 1.6;
      border-radius: 6px;
      background: var(--card-background-color);
      cursor: pointer;
      display: flex;
      align-items: flex-end;
      justify-content: center;
      transition: transform 0.05s ease;
    }
    .cell.off {
      background: var(--card-background-color);
      border: 1px dashed var(--secondary-text-color);
      opacity: 0.5;
    }
    .cell .cell-num {
      font-size: 9px;
      color: rgba(0, 0, 0, 0.55);
      padding-bottom: 2px;
      pointer-events: none;
    }
    .cell.sel {
      outline: 3px solid var(--primary-color);
      outline-offset: -1px;
      transform: translateY(-2px);
    }
    .cell.cursor::after {
      content: "";
      position: absolute;
      inset: -3px;
      border-radius: 8px;
      border: 2px dashed var(--primary-text-color);
      pointer-events: none;
    }
    /* Gradient */
    .gradient-bar {
      position: relative;
      height: 34px;
      border-radius: 17px;
      border: 1px solid var(--divider-color);
    }
    .handle {
      position: absolute;
      top: 50%;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      transform: translate(-50%, -50%);
      border: 2px solid var(--card-background-color);
      box-shadow: 0 0 0 1px var(--divider-color);
      cursor: grab;
      touch-action: none;
    }
    .handle.dragging {
      cursor: grabbing;
      transform: translate(-50%, -50%) scale(1.25);
    }
    .stops {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .stop {
      display: flex;
      align-items: center;
      gap: 2px;
    }
    /* Presets */
    .presets {
      gap: 8px;
    }
    .preset {
      display: inline-flex;
      flex-direction: column;
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 10px;
      cursor: pointer;
      font: inherit;
    }
    .preset:hover {
      border-color: var(--primary-color);
    }
    .preset .swatch {
      width: 64px;
      height: 22px;
      border-radius: 6px;
      border: 1px solid var(--divider-color);
    }
    .preset .preset-name {
      font-size: 0.8em;
      text-align: center;
      color: var(--secondary-text-color);
    }
    /* Preview */
    canvas.preview {
      width: 100%;
      height: 44px;
      display: block;
      border-radius: 8px;
      background: var(--card-background-color);
    }
    /* Controls */
    .btn {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 18px;
      padding: 6px 14px;
      font: inherit;
      cursor: pointer;
    }
    .btn:hover {
      border-color: var(--primary-color);
    }
    .btn.primary {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      border-color: var(--primary-color);
    }
    .btn.tiny {
      border-radius: 50%;
      width: 26px;
      height: 26px;
      padding: 0;
      line-height: 1;
    }
    .btn[disabled] {
      opacity: 0.4;
      cursor: not-allowed;
    }
    input[type="color"] {
      width: 42px;
      height: 30px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      background: var(--card-background-color);
      padding: 2px;
      cursor: pointer;
    }
    input[type="text"] {
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      padding: 7px 10px;
      font: inherit;
    }
    input[type="text"]:focus-visible {
      outline: none;
      border-color: var(--primary-color);
      box-shadow: 0 0 0 1px var(--primary-color);
    }
    .effect-name {
      flex: 1 1 12ch;
      min-width: 12ch;
    }
    /* Custom effects */
    .help {
      margin: 0;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    .feedback {
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 0.9em;
      border: 1px solid var(--divider-color);
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
    }
    .feedback.error {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .feedback.info {
      border-color: var(--success-color, var(--primary-color));
    }
    .effects {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .effect {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .effect-apply {
      flex: 1 1 auto;
      min-width: 0;
      display: flex;
      align-items: center;
      text-align: left;
    }
    .effect-label {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .effect.active .effect-apply {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      border-color: var(--primary-color);
    }
`;class K0 extends P{static properties={hass:{attribute:!1},_config:{state:!0}};setConfig(B){this._config={...B}}render(){return D`
      <div class="editor">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this._config?.entity??""}
          .includeDomains=${["light"]}
          .label=${"Light entity"}
          allow-custom-entity
          @value-changed=${this._entityChanged}
        ></ha-entity-picker>
        <p class="help">
          Choose a segment-capable Govee light (one exposing a
          <code>segment_colors</code> attribute).
        </p>
      </div>
    `}_entityChanged(B){let L=B.detail?.value??"",z={...this._config,entity:L};this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:z},bubbles:!0,composed:!0}))}static styles=b`
    .editor {
      padding: 8px;
    }
    .help {
      margin: 8px 0 0;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
  `}customElements.define("govee-led-ble-card-editor",K0);var W=15;function C(B,L,z){return Math.max(L,Math.min(z,B))}function x(B){let L=B.replace("#","");return[parseInt(L.slice(0,2),16),parseInt(L.slice(2,4),16),parseInt(L.slice(4,6),16)]}function r(B){return"#"+B.map((L)=>C(Math.round(L),0,255).toString(16).padStart(2,"0")).join("")}function m(B,L){if(B.length===0)throw Error("no stops");if(B.length===1){let q=B[0];return[q[0],q[1],q[2]]}let z=B.length-1,J=C(L,0,1)*z,Z=C(Math.floor(J),0,z-1),Q=J-Z,Y=B[Z],F=B[Z+1];return[Y[0]+(F[0]-Y[0])*Q,Y[1]+(F[1]-Y[1])*Q,Y[2]+(F[2]-Y[2])*Q]}function s0(B){let L=Math.floor(B),z=B-L;if(z<0.5)return L;if(z>0.5)return L+1;return L%2===0?L:L+1}function s(B,L=15){if(B.length===0)throw Error("no stops");if(L<=0)return[];if(B.length===1){let z=B[0];return Array.from({length:L},()=>[z[0],z[1],z[2]])}return Array.from({length:L},(z,J)=>{let Z=L>1?J/(L-1):0;return m(B,Z).map(s0)})}function e(B){let L=new Map,z=[];return B.forEach((J,Z)=>{let Q=`${J[0]},${J[1]},${J[2]}`,Y=L.get(Q);if(Y===void 0)Y={segments:[],rgb_color:[J[0],J[1],J[2]]},L.set(Q,Y),z.push(Y);Y.segments.push(Z+1)}),z}var U0=[{id:"sunset",name:"Sunset",stops:[[255,89,94],[255,146,76],[255,202,58]]},{id:"ocean",name:"Ocean",stops:[[15,32,89],[25,130,196],[112,193,179]]},{id:"forest",name:"Forest",stops:[[27,67,50],[45,106,79],[149,213,178]]},{id:"rainbow",name:"Rainbow",stops:[[255,0,0],[255,183,0],[0,200,83],[0,145,234],[170,0,255]]},{id:"warm-white",name:"Warm white",stops:[[255,183,107]]},{id:"cool-white",name:"Cool white",stops:[[188,220,255]]}];function M0(B,L=15){return e(s(B.stops,L))}function d0(B){return[...new Set(B)].sort((L,z)=>L-z)}function O0(B,L){let z=Math.min(B,L),J=Math.max(B,L),Z=new Set;for(let Q=z;Q<=J;Q++)Z.add(Q);return Z}function k0(B,L){let z=new Set(B);if(z.has(L))z.delete(L);else z.add(L);return z}function E0(B=15){let L=new Set;for(let z=1;z<=B;z++)L.add(z);return L}function t(){return new Set}function y0(B){if(B===null||typeof B!=="object"||Array.isArray(B))return[];let L=[];for(let[z,J]of Object.entries(B)){if(typeof J!=="string")continue;let Z=J.trim();if(Z==="")continue;L.push({id:z,name:Z})}return L.sort((z,J)=>{let Z=z.name.toLowerCase(),Q=J.name.toLowerCase();if(Z!==Q)return Z<Q?-1:1;if(z.id!==J.id)return z.id<J.id?-1:1;return 0}),L}function i(B){if(B!==null&&typeof B==="object"){let L=B.message;if(typeof L==="string"&&L.trim()!=="")return L}return null}function T(B,L="Something went wrong."){if(typeof B==="string"&&B.trim()!=="")return B;let z=i(B);if(z!==null)return z;if(B!==null&&typeof B==="object"){let J=B,Z=i(J.error)??i(J.body);if(Z!==null)return Z}return L}var e0=["#ff595e","#ffca3a","#1982c4"],t0="#33cc66",B0=2,L0=5;function B8(B){if(!Array.isArray(B))return null;let L=[];for(let z of B){if(!Array.isArray(z)||z.length<3)return null;let[J,Z,Q]=z;if(typeof J!=="number"||typeof Z!=="number"||typeof Q!=="number")return null;L.push([J,Z,Q])}return L}class N0 extends P{static properties={hass:{attribute:!1},_config:{state:!0},_selection:{state:!0},_cursor:{state:!0},_paintColor:{state:!0},_stops:{state:!0},_dragStop:{state:!0},_dragFrac:{state:!0},_reduce:{state:!0},_effectName:{state:!0},_renamingId:{state:!0},_renameValue:{state:!0},_feedback:{state:!0}};_dragging=!1;_dragAnchor=1;_raf=null;_t0=0;_mq;constructor(){super();this._selection=new Set,this._cursor=1,this._paintColor=t0,this._stops=[...e0],this._dragStop=null,this._dragFrac=null,this._reduce=!1,this._effectName="",this._renamingId=null,this._renameValue="",this._feedback=null}static getStubConfig(B){return{entity:(B?Object.keys(B.states).find((z)=>z.startsWith("light.")&&Array.isArray(B.states[z].attributes?.segment_colors)):void 0)??""}}static getConfigElement(){return document.createElement("govee-led-ble-card-editor")}setConfig(B){if(!B)throw Error("Invalid configuration");this._config={...B}}getCardSize(){return 10}connectedCallback(){super.connectedCallback();let B=window.matchMedia("(prefers-reduced-motion: reduce)");this._reduce=B.matches,this._mq=B,B.addEventListener("change",this._onReduceChange),this._raf=requestAnimationFrame((L)=>this._tick(L))}disconnectedCallback(){if(super.disconnectedCallback(),this._raf!==null)cancelAnimationFrame(this._raf);this._raf=null,this._mq?.removeEventListener("change",this._onReduceChange),window.removeEventListener("pointermove",this._onMove),window.removeEventListener("pointerup",this._onUp),window.removeEventListener("pointermove",this._onStopMove),window.removeEventListener("pointerup",this._onStopUp)}_onReduceChange=(B)=>{this._reduce=B.matches};_segmentColors(){let B=this._config?.entity;if(!B||!this.hass)return null;let L=this.hass.states[B];if(!L)return null;return B8(L.attributes?.segment_colors)}_cellFromClientX(B){let L=this.renderRoot.querySelector(".strip");if(!L)return 1;let z=L.getBoundingClientRect(),J=z.width/W;return C(Math.floor((B-z.left)/J),0,W-1)+1}_onDown(B){B.preventDefault(),this._dragging=!0,this._dragAnchor=this._cellFromClientX(B.clientX),this._cursor=this._dragAnchor,this._selection=new Set([this._dragAnchor]),this.renderRoot.querySelector(".strip")?.focus(),window.addEventListener("pointermove",this._onMove),window.addEventListener("pointerup",this._onUp)}_onMove=(B)=>{if(!this._dragging)return;let L=this._cellFromClientX(B.clientX);this._selection=O0(this._dragAnchor,L),this._cursor=L};_onUp=()=>{this._dragging=!1,window.removeEventListener("pointermove",this._onMove),window.removeEventListener("pointerup",this._onUp)};_onKey(B){let L=B.key;if(L==="ArrowRight"||L==="ArrowDown")this._cursor=C(this._cursor+1,1,W),B.preventDefault();else if(L==="ArrowLeft"||L==="ArrowUp")this._cursor=C(this._cursor-1,1,W),B.preventDefault();else if(L==="Home")this._cursor=1,B.preventDefault();else if(L==="End")this._cursor=W,B.preventDefault();else if(L===" "||L==="Spacebar")this._selection=k0(this._selection,this._cursor),B.preventDefault();else if(L==="Enter")this._applyPaint(),B.preventDefault();else if(L==="Escape")this._dragging=!1,this._selection=t(),B.preventDefault()}_selectAll(){this._selection=E0(W)}_clear(){this._selection=t()}_applyPaint(){let B=this._config?.entity;if(!this.hass||!B||this._selection.size===0)return;let L=[{segments:d0(this._selection),rgb_color:x(this._paintColor)}];this.hass.callService("ha_govee_led_ble","paint_segments",{groups:L},{entity_id:B})}_addStop(){if(this._stops.length>=L0)return;let B=m(this._stops.map(x),0.5);this._stops=[...this._stops,r(B)]}_removeStop(B){if(this._stops.length<=B0)return;this._stops=this._stops.filter((L,z)=>z!==B)}_recolourStop(B,L){let z=[...this._stops];z[B]=L,this._stops=z}_stopTargetIndex(B){let L=this.renderRoot.querySelector(".gradient-bar");if(!L)return this._dragStop??0;let z=L.getBoundingClientRect(),J=C((B-z.left)/z.width,0,1);return C(Math.round(J*(this._stops.length-1)),0,this._stops.length-1)}_startStopDrag(B,L){B.preventDefault(),this._dragStop=L,window.addEventListener("pointermove",this._onStopMove),window.addEventListener("pointerup",this._onStopUp)}_onStopMove=(B)=>{if(this._dragStop===null)return;let L=this.renderRoot.querySelector(".gradient-bar");if(!L)return;let z=L.getBoundingClientRect();this._dragFrac=C((B.clientX-z.left)/z.width,0,1)};_onStopUp=(B)=>{if(this._dragStop===null)return;let L=this._dragStop,z=this._stopTargetIndex(B.clientX);if(L!==z){let J=[...this._stops],[Z]=J.splice(L,1);J.splice(z,0,Z),this._stops=J}this._dragStop=null,this._dragFrac=null,window.removeEventListener("pointermove",this._onStopMove),window.removeEventListener("pointerup",this._onStopUp)};_applyGradient(){let B=this._config?.entity;if(!this.hass||!B)return;let L=e(s(this._stops.map(x),W));this.hass.callService("ha_govee_led_ble","paint_segments",{groups:L},{entity_id:B})}_applyPreset(B){let L=this._config?.entity;if(!this.hass||!L)return;this.hass.callService("ha_govee_led_ble","paint_segments",{groups:M0(B)},{entity_id:L})}_presetSwatch(B){if(B.length===1){let[z,J,Z]=B[0];return`rgb(${z},${J},${Z})`}return`linear-gradient(90deg, ${B.map(([z,J,Z],Q)=>`rgb(${z},${J},${Z}) ${Q/(B.length-1)*100}%`).join(", ")})`}async _saveEffect(){let B=this._config?.entity;if(!this.hass||!B)return;let L=this._effectName.trim();try{await this.hass.callService("ha_govee_led_ble","save_effect",{name:L,capture_current:!0},{entity_id:B}),this._effectName="",this._feedback={kind:"info",text:`Saved "${L}".`}}catch(z){this._feedback={kind:"error",text:T(z)}}}async _applyEffect(B){let L=this._config?.entity;if(!this.hass||!L)return;this._feedback=null;try{await this.hass.callService("light","turn_on",{effect:B.name},{entity_id:L})}catch(z){this._feedback={kind:"error",text:T(z)}}}_startRename(B){this._feedback=null,this._renamingId=B.id,this._renameValue=B.name,this.updateComplete.then(()=>{let L=this.renderRoot.querySelector(".rename-input");L?.focus(),L?.select()})}_cancelRename(){this._renamingId=null,this._renameValue=""}async _commitRename(B){let L=this._config?.entity;if(!this.hass||!L)return;let z=this._renameValue.trim();try{await this.hass.callService("ha_govee_led_ble","rename_effect",{id:B.id,to:z},{entity_id:L}),this._renamingId=null,this._renameValue="",this._feedback={kind:"info",text:`Renamed to "${z}".`}}catch(J){this._feedback={kind:"error",text:T(J)}}}async _deleteEffect(B){let L=this._config?.entity;if(!this.hass||!L)return;if(this._renamingId===B.id)this._cancelRename();try{await this.hass.callService("ha_govee_led_ble","delete_effect",{id:B.id},{entity_id:L}),this._feedback={kind:"info",text:`Deleted "${B.name}".`}}catch(z){this._feedback={kind:"error",text:T(z)}}}_onEffectNameKey(B){if(B.key==="Enter")B.preventDefault(),this._saveEffect()}_onRenameKey(B,L){if(B.key==="Enter")B.preventDefault(),this._commitRename(L);else if(B.key==="Escape")B.preventDefault(),this._cancelRename()}_tick(B){if(!this._t0)this._t0=B;let L=this.renderRoot?.querySelector("canvas.preview");if(L)this._draw(L,(B-this._t0)/1000);this._raf=requestAnimationFrame((z)=>this._tick(z))}_draw(B,L){let z=window.devicePixelRatio||1,J=B.clientWidth||480,Z=B.clientHeight||44;if(B.width!==Math.round(J*z))B.width=Math.round(J*z),B.height=Math.round(Z*z);let Q=B.getContext("2d");if(!Q)return;Q.setTransform(z,0,0,z,0,0),Q.clearRect(0,0,J,Z);let Y=this._stops.map(x),F=W,q=this._reduce?0:L*0.25,A=3,V=(J-A*(F-1))/F;for(let j=0;j<F;j++){let $=this._reduce?j/(F-1):((j/F+q)%1+1)%1,I=m(Y,$);Q.fillStyle=`rgb(${I.map((T0)=>Math.round(T0)).join(",")})`;let x0=j*(V+A);Q.beginPath(),Q.roundRect(x0,0,V,Z,4),Q.fill()}}render(){if(!this._config)return H;let B=this._config.entity;if(!B)return this._notice("Select a light entity in the card configuration.");let L=this.hass?.states?.[B];if(!L||L.state==="unavailable"||L.state==="unknown")return this._notice(`${B} is unavailable.`);let z=this._segmentColors();if(!z)return this._notice(`${B} exposes no segment colours; this model has no addressable segments.`);let J=`linear-gradient(90deg, ${this._stops.map((Z,Q)=>`${Z} ${Q/(this._stops.length-1)*100}%`).join(", ")})`;return D`
      <ha-card header="Govee segment painter">
        <div class="body">
          ${this._renderPainter(z)}
          ${this._renderGradient(J)}
          ${this._renderPresets()}
          ${this._renderEffects(L)}
          ${this._renderPreview()}
        </div>
      </ha-card>
    `}_notice(B){return D`
      <ha-card header="Govee segment painter">
        <div class="notice">${B}</div>
      </ha-card>
    `}_renderPainter(B){let L=[];for(let z=1;z<=W;z++){let J=B[z-1],Z=J?r(J):null,Q=this._selection.has(z),Y=z===this._cursor;L.push(D`
        <div
          class="cell ${Q?"sel":""} ${Y?"cursor":""} ${Z?"":"off"}"
          style=${Z?`background:${Z}`:""}
          role="option"
          aria-selected=${Q?"true":"false"}
          aria-label=${`Segment ${z}`}
          title=${`Segment ${z}`}
        >
          <span class="cell-num">${z}</span>
        </div>
      `)}return D`
      <section>
        <div class="row heading">
          <span class="label">Segment painter</span>
          <span class="hint">${this._selection.size} selected</span>
        </div>
        <div
          class="strip"
          style="grid-template-columns: repeat(${W}, 1fr)"
          tabindex="0"
          role="listbox"
          aria-multiselectable="true"
          aria-label=${`Segment painter, ${W} segments`}
          @pointerdown=${this._onDown}
          @keydown=${this._onKey}
        >
          ${L}
        </div>
        <div class="row controls">
          <input
            type="color"
            aria-label="Paint colour"
            .value=${this._paintColor}
            @input=${(z)=>this._paintColor=z.target.value}
          />
          <button class="btn primary" @click=${this._applyPaint}>
            Apply to selection
          </button>
          <button class="btn" @click=${this._selectAll}>Select all</button>
          <button class="btn" @click=${this._clear}>Clear</button>
        </div>
      </section>
    `}_renderGradient(B){let L=this._stops.length;return D`
      <section>
        <div class="row heading">
          <span class="label">Gradient stops</span>
          <span class="hint">${L} of ${B0} to ${L0}</span>
        </div>
        <div class="gradient-bar" style="background:${B}">
          ${this._stops.map((z,J)=>D`
              <div
                class="handle ${this._dragStop===J?"dragging":""}"
                style="left:${this._dragStop===J&&this._dragFrac!==null?this._dragFrac*100:J/(L-1)*100}%;background:${z}"
                @pointerdown=${(Z)=>this._startStopDrag(Z,J)}
                title=${`Stop ${J+1}`}
              ></div>
            `)}
        </div>
        <div class="stops">
          ${this._stops.map((z,J)=>D`
              <div class="stop">
                <input
                  type="color"
                  aria-label=${`Stop ${J+1} colour`}
                  .value=${z}
                  @input=${(Z)=>this._recolourStop(J,Z.target.value)}
                />
                <button
                  class="btn tiny"
                  ?disabled=${L<=B0}
                  @click=${()=>this._removeStop(J)}
                  title="Remove stop"
                >
                  &times;
                </button>
              </div>
            `)}
          <button
            class="btn tiny add"
            ?disabled=${L>=L0}
            @click=${this._addStop}
            title="Add stop"
          >
            +
          </button>
        </div>
        <div class="row controls">
          <button class="btn primary" @click=${this._applyGradient}>
            Apply gradient
          </button>
        </div>
      </section>
    `}_renderPresets(){return D`
      <section>
        <div class="row heading">
          <span class="label">Presets</span>
        </div>
        <div class="row presets">
          ${U0.map((B)=>D`
              <button
                class="preset"
                @click=${()=>this._applyPreset(B)}
                title=${B.name}
                aria-label=${B.name}
              >
                <span
                  class="swatch"
                  style="background:${this._presetSwatch(B.stops)}"
                ></span>
                <span class="preset-name">${B.name}</span>
              </button>
            `)}
        </div>
      </section>
    `}_renderPreview(){return D`
      <section>
        <div class="row heading">
          <span class="label">Live preview</span>
        </div>
        <canvas class="preview" height="44"></canvas>
      </section>
    `}_renderEffects(B){let L=y0(B.attributes?.custom_effects),z=typeof B.attributes?.effect==="string"?B.attributes.effect:null;return D`
      <section>
        <div class="row heading">
          <span class="label">Custom effects</span>
          <span class="hint">${L.length} saved</span>
        </div>
        <div class="row controls">
          <input
            class="effect-name"
            type="text"
            aria-label="New effect name"
            placeholder="New effect name"
            .value=${this._effectName}
            @input=${(J)=>this._effectName=J.target.value}
            @keydown=${this._onEffectNameKey}
          />
          <button class="btn primary" @click=${this._saveEffect}>
            Save as effect
          </button>
        </div>
        <p class="help">Saves the strip's current colours as a named effect.</p>
        ${this._feedback?D`<div class="feedback ${this._feedback.kind}" role="alert">
              ${this._feedback.text}
            </div>`:H}
        ${L.length===0?D`<p class="help">No custom effects saved yet.</p>`:D`<ul class="effects" role="list">
              ${L.map((J)=>this._renderEffectRow(J,z))}
            </ul>`}
      </section>
    `}_renderEffectRow(B,L){if(this._renamingId===B.id)return D`
        <li class="effect renaming">
          <input
            class="effect-name rename-input"
            type="text"
            aria-label=${`New name for ${B.name}`}
            .value=${this._renameValue}
            @input=${(J)=>this._renameValue=J.target.value}
            @keydown=${(J)=>this._onRenameKey(J,B)}
          />
          <button class="btn primary" @click=${()=>this._commitRename(B)}>
            Save
          </button>
          <button class="btn" @click=${this._cancelRename}>Cancel</button>
        </li>
      `;let z=L!==null&&L===B.name;return D`
      <li class="effect ${z?"active":""}">
        <button
          class="btn effect-apply"
          @click=${()=>this._applyEffect(B)}
          aria-label=${`Apply ${B.name}`}
          aria-pressed=${z?"true":"false"}
          title=${`Apply ${B.name}`}
        >
          <span class="effect-label">${B.name}</span>
        </button>
        <button
          class="btn"
          @click=${()=>this._startRename(B)}
          aria-label=${`Rename ${B.name}`}
        >
          Rename
        </button>
        <button
          class="btn"
          @click=${()=>this._deleteEffect(B)}
          aria-label=${`Delete ${B.name}`}
        >
          Delete
        </button>
      </li>
    `}static styles=_0}customElements.define("govee-led-ble-card",N0);window.customCards=window.customCards||[];window.customCards.push({type:"govee-led-ble-card",name:"Govee LED BLE",description:"Drag-paint segments and edit a colour-stop gradient for the ha_govee_led_ble integration.",preview:!1});console.info("%c govee-led-ble-card ","background:#1982c4;color:#fff;border-radius:3px","loaded");
