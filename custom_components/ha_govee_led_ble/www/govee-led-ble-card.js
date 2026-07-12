var x=globalThis,pw=x.ShadowRoot&&(x.ShadyCSS===void 0||x.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,mw=Symbol(),Xw=new WeakMap;class Ew{constructor(w,r,u){if(this._$cssResult$=!0,u!==mw)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=w,this.t=r}get styleSheet(){let w=this.i,r=this.t;if(pw&&w===void 0){let u=r!==void 0&&r.length===1;u&&(w=Xw.get(r)),w===void 0&&((this.i=w=new CSSStyleSheet).replaceSync(this.cssText),u&&Xw.set(r,w))}return w}toString(){return this.cssText}}var Yr=(w)=>new Ew(typeof w=="string"?w:w+"",void 0,mw),e=(w,...r)=>{let u=w.length===1?w[0]:r.reduce((o,$,b)=>o+((p)=>{if(p._$cssResult$===!0)return p.cssText;if(typeof p=="number")return p;throw Error("Value passed to 'css' function must be a 'css' function result: "+p+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})($)+w[b+1],w[0]);return new Ew(u,w,mw)},Fr=(w,r)=>{if(pw)w.adoptedStyleSheets=r.map((u)=>u instanceof CSSStyleSheet?u:u.styleSheet);else for(let u of r){let o=document.createElement("style"),$=x.litNonce;$!==void 0&&o.setAttribute("nonce",$),o.textContent=u.cssText,w.appendChild(o)}},Gw=pw?(w)=>w:(w)=>w instanceof CSSStyleSheet?((r)=>{let u="";for(let o of r.cssRules)u+=o.cssText;return Yr(u)})(w):w,{is:Dr,defineProperty:Wr,getOwnPropertyDescriptor:kr,getOwnPropertyNames:Cr,getOwnPropertySymbols:Xr,getPrototypeOf:Gr}=Object,t=globalThis,gw=t.trustedTypes,gr=gw?gw.emptyScript:"",_r=t.reactiveElementPolyfillSupport,N=(w,r)=>w,bw={toAttribute(w,r){switch(r){case Boolean:w=w?gr:null;break;case Object:case Array:w=w==null?w:JSON.stringify(w)}return w},fromAttribute(w,r){let u=w;switch(r){case Boolean:u=w!==null;break;case Number:u=w===null?null:Number(w);break;case Object:case Array:try{u=JSON.parse(w)}catch(o){u=null}}return u}},Uw=(w,r)=>!Dr(w,r),_w={attribute:!0,type:String,converter:bw,reflect:!1,useDefault:!1,hasChanged:Uw};Symbol.metadata??=Symbol("metadata"),t.litPropertyMetadata??=new WeakMap;class H extends HTMLElement{static addInitializer(w){this.o(),(this.l??=[]).push(w)}static get observedAttributes(){return this.finalize(),this.u&&[...this.u.keys()]}static createProperty(w,r=_w){if(r.state&&(r.attribute=!1),this.o(),this.prototype.hasOwnProperty(w)&&((r=Object.create(r)).wrapped=!0),this.elementProperties.set(w,r),!r.noAccessor){let u=Symbol(),o=this.getPropertyDescriptor(w,u,r);o!==void 0&&Wr(this.prototype,w,o)}}static getPropertyDescriptor(w,r,u){let{get:o,set:$}=kr(this.prototype,w)??{get(){return this[r]},set(b){this[r]=b}};return{get:o,set(b){let p=o?.call(this);$?.call(this,b),this.requestUpdate(w,p,u)},configurable:!0,enumerable:!0}}static getPropertyOptions(w){return this.elementProperties.get(w)??_w}static o(){if(this.hasOwnProperty(N("elementProperties")))return;let w=Gr(this);w.finalize(),w.l!==void 0&&(this.l=[...w.l]),this.elementProperties=new Map(w.elementProperties)}static finalize(){if(this.hasOwnProperty(N("finalized")))return;if(this.finalized=!0,this.o(),this.hasOwnProperty(N("properties"))){let r=this.properties,u=[...Cr(r),...Xr(r)];for(let o of u)this.createProperty(o,r[o])}let w=this[Symbol.metadata];if(w!==null){let r=litPropertyMetadata.get(w);if(r!==void 0)for(let[u,o]of r)this.elementProperties.set(u,o)}this.u=new Map;for(let[r,u]of this.elementProperties){let o=this.p(r,u);o!==void 0&&this.u.set(o,r)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(w){let r=[];if(Array.isArray(w)){let u=new Set(w.flat(1/0).reverse());for(let o of u)r.unshift(Gw(o))}else w!==void 0&&r.push(Gw(w));return r}static p(w,r){let u=r.attribute;return u===!1?void 0:typeof u=="string"?u:typeof w=="string"?w.toLowerCase():void 0}constructor(){super(),this.v=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this.m=null,this._()}_(){this.S=new Promise((w)=>this.enableUpdating=w),this._$AL=new Map,this.$(),this.requestUpdate(),this.constructor.l?.forEach((w)=>w(this))}addController(w){(this.P??=new Set).add(w),this.renderRoot!==void 0&&this.isConnected&&w.hostConnected?.()}removeController(w){this.P?.delete(w)}$(){let w=new Map,r=this.constructor.elementProperties;for(let u of r.keys())this.hasOwnProperty(u)&&(w.set(u,this[u]),delete this[u]);w.size>0&&(this.v=w)}createRenderRoot(){let w=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Fr(w,this.constructor.elementStyles),w}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this.P?.forEach((w)=>w.hostConnected?.())}enableUpdating(w){}disconnectedCallback(){this.P?.forEach((w)=>w.hostDisconnected?.())}attributeChangedCallback(w,r,u){this._$AK(w,u)}C(w,r){let u=this.constructor.elementProperties.get(w),o=this.constructor.p(w,u);if(o!==void 0&&u.reflect===!0){let $=(u.converter?.toAttribute!==void 0?u.converter:bw).toAttribute(r,u.type);this.m=w,$==null?this.removeAttribute(o):this.setAttribute(o,$),this.m=null}}_$AK(w,r){let u=this.constructor,o=u.u.get(w);if(o!==void 0&&this.m!==o){let $=u.getPropertyOptions(o),b=typeof $.converter=="function"?{fromAttribute:$.converter}:$.converter?.fromAttribute!==void 0?$.converter:bw;this.m=o;let p=b.fromAttribute(r,$.type);this[o]=p??this.T?.get(o)??p,this.m=null}}requestUpdate(w,r,u,o=!1,$){if(w!==void 0){let b=this.constructor;if(o===!1&&($=this[w]),u??=b.getPropertyOptions(w),!((u.hasChanged??Uw)($,r)||u.useDefault&&u.reflect&&$===this.T?.get(w)&&!this.hasAttribute(b.p(w,u))))return;this.M(w,r,u)}this.isUpdatePending===!1&&(this.S=this.k())}M(w,r,{useDefault:u,reflect:o,wrapped:$},b){u&&!(this.T??=new Map).has(w)&&(this.T.set(w,b??r??this[w]),$!==!0||b!==void 0)||(this._$AL.has(w)||(this.hasUpdated||u||(r=void 0),this._$AL.set(w,r)),o===!0&&this.m!==w&&(this.A??=new Set).add(w))}async k(){this.isUpdatePending=!0;try{await this.S}catch(r){Promise.reject(r)}let w=this.scheduleUpdate();return w!=null&&await w,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this.v){for(let[o,$]of this.v)this[o]=$;this.v=void 0}let u=this.constructor.elementProperties;if(u.size>0)for(let[o,$]of u){let{wrapped:b}=$,p=this[o];b!==!0||this._$AL.has(o)||p===void 0||this.M(o,void 0,$,p)}}let w=!1,r=this._$AL;try{w=this.shouldUpdate(r),w?(this.willUpdate(r),this.P?.forEach((u)=>u.hostUpdate?.()),this.update(r)):this.U()}catch(u){throw w=!1,this.U(),u}w&&this._$AE(r)}willUpdate(w){}_$AE(w){this.P?.forEach((r)=>r.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(w)),this.updated(w)}U(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this.S}shouldUpdate(w){return!0}update(w){this.A&&=this.A.forEach((r)=>this.C(r,this[r])),this.U()}updated(w){}firstUpdated(w){}}H.elementStyles=[],H.shadowRootOptions={mode:"open"},H[N("elementProperties")]=new Map,H[N("finalized")]=new Map,_r?.({ReactiveElement:H}),(t.reactiveElementVersions??=[]).push("2.1.2");var nw=globalThis,Hw=(w)=>w,s=nw.trustedTypes,Pw=s?s.createPolicy("lit-html",{createHTML:(w)=>w}):void 0,Aw="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,Iw="?"+C,Hr=`<${Iw}>`,L=document,S=()=>L.createComment(""),f=(w)=>w===null||typeof w!="object"&&typeof w!="function",Bw=Array.isArray,Pr=(w)=>Bw(w)||typeof w?.[Symbol.iterator]=="function",$w=`[ 	
\f\r]`,O=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Lw=/-->/g,Kw=/>/g,_=RegExp(`>|${$w}(?:([^\\s"'>=/]+)(${$w}*=${$w}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),hw=/'/g,Mw=/"/g,lw=/^(?:script|style|textarea|title)$/i,Jw=(w)=>(r,...u)=>({_$litType$:w,strings:r,values:u}),m=Jw(1),Sr=Jw(2),fr=Jw(3),h=Symbol.for("lit-noChange"),J=Symbol.for("lit-nothing"),aw=new WeakMap,P=L.createTreeWalker(L,129);function yw(w,r){if(!Bw(w)||!w.hasOwnProperty("raw"))throw Error("invalid template strings array");return Pw!==void 0?Pw.createHTML(r):r}var Lr=(w,r)=>{let u=w.length-1,o=[],$,b=r===2?"<svg>":r===3?"<math>":"",p=O;for(let n=0;n<u;n++){let E=w[n],q,B,z=-1,Q=0;for(;Q<E.length&&(p.lastIndex=Q,B=p.exec(E),B!==null);)Q=p.lastIndex,p===O?B[1]==="!--"?p=Lw:B[1]!==void 0?p=Kw:B[2]!==void 0?(lw.test(B[2])&&($=RegExp("</"+B[2],"g")),p=_):B[3]!==void 0&&(p=_):p===_?B[0]===">"?(p=$??O,z=-1):B[1]===void 0?z=-2:(z=p.lastIndex-B[2].length,q=B[1],p=B[3]===void 0?_:B[3]==='"'?Mw:hw):p===Mw||p===hw?p=_:p===Lw||p===Kw?p=O:(p=_,$=void 0);let g=p===_&&w[n+1].startsWith("/>")?" ":"";b+=p===O?E+Hr:z>=0?(o.push(q),E.slice(0,z)+Aw+E.slice(z)+C+g):E+C+(z===-2?n:g)}return[yw(w,b+(w[u]||"<?>")+(r===2?"</svg>":r===3?"</math>":"")),o]};class v{constructor({strings:w,_$litType$:r},u){let o;this.parts=[];let $=0,b=0,p=w.length-1,n=this.parts,[E,q]=Lr(w,r);if(this.el=v.createElement(E,u),P.currentNode=this.el.content,r===2||r===3){let B=this.el.content.firstChild;B.replaceWith(...B.childNodes)}for(;(o=P.nextNode())!==null&&n.length<p;){if(o.nodeType===1){if(o.hasAttributes())for(let B of o.getAttributeNames())if(B.endsWith(Aw)){let z=q[b++],Q=o.getAttribute(B).split(C),g=/([.?@])?(.*)/.exec(z);n.push({type:1,index:$,name:g[2],strings:Q,ctor:g[1]==="."?Nw:g[1]==="?"?Sw:g[1]==="@"?fw:T}),o.removeAttribute(B)}else B.startsWith(C)&&(n.push({type:6,index:$}),o.removeAttribute(B));if(lw.test(o.tagName)){let B=o.textContent.split(C),z=B.length-1;if(z>0){o.textContent=s?s.emptyScript:"";for(let Q=0;Q<z;Q++)o.append(B[Q],S()),P.nextNode(),n.push({type:2,index:++$});o.append(B[z],S())}}}else if(o.nodeType===8)if(o.data===Iw)n.push({type:2,index:$});else{let B=-1;for(;(B=o.data.indexOf(C,B+1))!==-1;)n.push({type:7,index:$}),B+=C.length-1}$++}}static createElement(w,r){let u=L.createElement("template");return u.innerHTML=w,u}}function M(w,r,u=w,o){if(r===h)return r;let $=o!==void 0?u.N?.[o]:u.O,b=f(r)?void 0:r._$litDirective$;return $?.constructor!==b&&($?._$AO?.(!1),b===void 0?$=void 0:($=new b(w),$._$AT(w,u,o)),o!==void 0?(u.N??=[])[o]=$:u.O=$),$!==void 0&&(r=M(w,$._$AS(w,r.values),$,o)),r}class Ow{constructor(w,r){this._$AV=[],this._$AN=void 0,this._$AD=w,this._$AM=r}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}R(w){let{el:{content:r},parts:u}=this._$AD,o=(w?.creationScope??L).importNode(r,!0);P.currentNode=o;let $=P.nextNode(),b=0,p=0,n=u[0];for(;n!==void 0;){if(b===n.index){let E;n.type===2?E=new d($,$.nextSibling,this,w):n.type===1?E=new n.ctor($,n.name,n.strings,this,w):n.type===6&&(E=new vw($,this,w)),this._$AV.push(E),n=u[++p]}b!==n?.index&&($=P.nextNode(),b++)}return P.currentNode=L,o}V(w){let r=0;for(let u of this._$AV)u!==void 0&&(u.strings!==void 0?(u._$AI(w,u,r),r+=u.strings.length-2):u._$AI(w[r])),r++}}class d{get _$AU(){return this._$AM?._$AU??this.D}constructor(w,r,u,o){this.type=2,this._$AH=J,this._$AN=void 0,this._$AA=w,this._$AB=r,this._$AM=u,this.options=o,this.D=o?.isConnected??!0}get parentNode(){let w=this._$AA.parentNode,r=this._$AM;return r!==void 0&&w?.nodeType===11&&(w=r.parentNode),w}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(w,r=this){w=M(this,w,r),f(w)?w===J||w==null||w===""?(this._$AH!==J&&this._$AR(),this._$AH=J):w!==this._$AH&&w!==h&&this.L(w):w._$litType$!==void 0?this.j(w):w.nodeType!==void 0?this.I(w):Pr(w)?this.H(w):this.L(w)}B(w){return this._$AA.parentNode.insertBefore(w,this._$AB)}I(w){this._$AH!==w&&(this._$AR(),this._$AH=this.B(w))}L(w){this._$AH!==J&&f(this._$AH)?this._$AA.nextSibling.data=w:this.I(L.createTextNode(w)),this._$AH=w}j(w){let{values:r,_$litType$:u}=w,o=typeof u=="number"?this._$AC(w):(u.el===void 0&&(u.el=v.createElement(yw(u.h,u.h[0]),this.options)),u);if(this._$AH?._$AD===o)this._$AH.V(r);else{let $=new Ow(o,this),b=$.R(this.options);$.V(r),this.I(b),this._$AH=$}}_$AC(w){let r=aw.get(w.strings);return r===void 0&&aw.set(w.strings,r=new v(w)),r}H(w){Bw(this._$AH)||(this._$AH=[],this._$AR());let r=this._$AH,u,o=0;for(let $ of w)o===r.length?r.push(u=new d(this.B(S()),this.B(S()),this,this.options)):u=r[o],u._$AI($),o++;o<r.length&&(this._$AR(u&&u._$AB.nextSibling,o),r.length=o)}_$AR(w=this._$AA.nextSibling,r){for(this._$AP?.(!1,!0,r);w!==this._$AB;){let u=Hw(w).nextSibling;Hw(w).remove(),w=u}}setConnected(w){this._$AM===void 0&&(this.D=w,this._$AP?.(w))}}class T{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(w,r,u,o,$){this.type=1,this._$AH=J,this._$AN=void 0,this.element=w,this.name=r,this._$AM=o,this.options=$,u.length>2||u[0]!==""||u[1]!==""?(this._$AH=Array(u.length-1).fill(new String),this.strings=u):this._$AH=J}_$AI(w,r=this,u,o){let $=this.strings,b=!1;if($===void 0)w=M(this,w,r,0),b=!f(w)||w!==this._$AH&&w!==h,b&&(this._$AH=w);else{let p=w,n,E;for(w=$[0],n=0;n<$.length-1;n++)E=M(this,p[u+n],r,n),E===h&&(E=this._$AH[n]),b||=!f(E)||E!==this._$AH[n],E===J?w=J:w!==J&&(w+=(E??"")+$[n+1]),this._$AH[n]=E}b&&!o&&this.W(w)}W(w){w===J?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,w??"")}}class Nw extends T{constructor(){super(...arguments),this.type=3}W(w){this.element[this.name]=w===J?void 0:w}}class Sw extends T{constructor(){super(...arguments),this.type=4}W(w){this.element.toggleAttribute(this.name,!!w&&w!==J)}}class fw extends T{constructor(w,r,u,o,$){super(w,r,u,o,$),this.type=5}_$AI(w,r=this){if((w=M(this,w,r,0)??J)===h)return;let u=this._$AH,o=w===J&&u!==J||w.capture!==u.capture||w.once!==u.once||w.passive!==u.passive,$=w!==J&&(u===J||o);o&&this.element.removeEventListener(this.name,this,u),$&&this.element.addEventListener(this.name,this,w),this._$AH=w}handleEvent(w){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,w):this._$AH.handleEvent(w)}}class vw{constructor(w,r,u){this.element=w,this.type=6,this._$AN=void 0,this._$AM=r,this.options=u}get _$AU(){return this._$AM._$AU}_$AI(w){M(this,w)}}var Kr=nw.litHtmlPolyfillSupport;Kr?.(v,d),(nw.litHtmlVersions??=[]).push("3.3.3");var hr=(w,r,u)=>{let o=u?.renderBefore??r,$=o._$litPart$;if($===void 0){let b=u?.renderBefore??null;o._$litPart$=$=new d(r.insertBefore(S(),b),b,void 0,u??{})}return $._$AI(w),$},Rw=globalThis;class W extends H{constructor(){super(...arguments),this.renderOptions={host:this},this.rt=void 0}createRenderRoot(){let w=super.createRenderRoot();return this.renderOptions.renderBefore??=w.firstChild,w}update(w){let r=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(w),this.rt=hr(r,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this.rt?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this.rt?.setConnected(!1)}render(){return h}}W._$litElement$=!0,W.finalized=!0,Rw.litElementHydrateSupport?.({LitElement:W});var Mr=Rw.litElementPolyfillSupport;Mr?.({LitElement:W});(Rw.litElementVersions??=[]).push("4.2.2");var dw=e`
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
      touch-action: pan-x pan-y;
      user-select: none;
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
      line-height: 1.2;
      font-weight: 600;
      padding: 1px 4px;
      margin-bottom: 2px;
      border-radius: 6px;
      background: rgba(0, 0, 0, 0.4);
      color: #fff;
      pointer-events: none;
    }
    .cell.off .cell-num,
    .cell.unchanged .cell-num {
      background: var(--card-background-color);
      color: var(--secondary-text-color);
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
      width: 28px;
      height: 28px;
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
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--divider-color);
      border-radius: 9px;
      background: var(--secondary-background-color);
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
    .btn.primary[disabled] {
      opacity: 1;
      background: var(--disabled-color, var(--divider-color));
      color: var(--disabled-text-color, var(--secondary-text-color));
      border-color: var(--divider-color);
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
    textarea {
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      padding: 10px;
      font: 0.85em/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
      resize: vertical;
    }
    textarea:focus-visible {
      outline: none;
      border-color: var(--primary-color);
      box-shadow: 0 0 0 1px var(--primary-color);
    }
    .effect-name {
      flex: 1 1 12ch;
      min-width: 12ch;
    }
    .edit-band {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 10px;
      border: 1px solid var(--primary-color);
      border-radius: 8px;
      color: var(--primary-text-color);
      background: var(--secondary-background-color);
      font-size: 0.85em;
    }
    .pending-author {
      padding: 12px;
      border: 1px dashed var(--divider-color);
      border-radius: 10px;
      background: var(--secondary-background-color);
    }
    .import-panel {
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      overflow: hidden;
    }
    .import-panel summary {
      padding: 10px 12px;
      color: var(--primary-text-color);
      font-weight: 600;
      cursor: pointer;
    }
    .import-panel[open] summary {
      border-bottom: 1px solid var(--divider-color);
    }
    .import-body {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 12px;
    }
    .import-json {
      min-height: 130px;
    }
    .import-file {
      display: none;
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
    .draft-confirm {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 10px;
      border: 1px solid var(--warning-color, #f9a825);
      border-radius: 8px;
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
      font-size: 0.9em;
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
      flex-wrap: wrap;
    }
    .effect-main {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1 1 220px;
      min-width: 0;
    }
    .effect-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 6px;
      flex: 1 1 auto;
      flex-wrap: wrap;
    }
    .effect-more summary {
      list-style: none;
    }
    .effect-more summary::-webkit-details-marker {
      display: none;
    }
    .effect-more[open] {
      flex-basis: 100%;
    }
    .more-actions {
      display: flex;
      justify-content: flex-end;
      gap: 6px;
      margin-top: 6px;
      flex-wrap: wrap;
    }
    .effect-label {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--primary-text-color);
    }
    /* Studio shell: header, status band, tabs */
    .card-head {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 16px 16px 0;
    }
    .title {
      font-size: 1.15em;
      font-weight: 600;
      color: var(--primary-text-color);
    }
    .status {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--secondary-text-color);
      font-size: 0.9em;
      min-width: 0;
    }
    .status .current {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--primary-text-color);
    }
    .tabs {
      display: flex;
      gap: 4px;
      background: var(--divider-color);
      border-radius: 22px;
      padding: 4px;
    }
    .tab {
      flex: 1 1 0;
      border: none;
      background: transparent;
      color: var(--secondary-text-color);
      border-radius: 18px;
      padding: 8px 12px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    .tab:hover {
      color: var(--primary-text-color);
    }
    .tab.active {
      background: var(--card-background-color);
      color: var(--primary-text-color);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18);
    }
    .tab:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    /* Studio: kind pill picker */
    .kinds {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .kind {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 16px;
      padding: 6px 14px;
      font: inherit;
      cursor: pointer;
    }
    .kind:hover {
      border-color: var(--primary-color);
    }
    .kind.active {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      border-color: var(--primary-color);
    }
    .kind.soon,
    .kind:disabled {
      opacity: 1;
      border-style: dashed;
      background: var(--secondary-background-color);
      color: var(--secondary-text-color);
      cursor: default;
    }
    .kind.soon:hover,
    .kind:disabled:hover {
      border-color: var(--divider-color);
    }
    .kind .soon-tag {
      font-size: 0.7em;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      background: var(--divider-color);
      color: var(--secondary-text-color);
      border-radius: 8px;
      padding: 1px 6px;
      margin-left: 6px;
    }
    .kind:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    /* Studio: unchanged (leave-as-is) segment cells */
    .cell.unchanged {
      background:
        repeating-linear-gradient(
          45deg,
          transparent,
          transparent 5px,
          var(--divider-color) 5px,
          var(--divider-color) 6px
        ),
        var(--card-background-color);
      border: 1px solid var(--divider-color);
    }
    .cell.background {
      background:
        repeating-linear-gradient(
          45deg,
          transparent,
          transparent 5px,
          rgba(255, 255, 255, 0.24) 5px,
          rgba(255, 255, 255, 0.24) 6px
        ),
        var(--cell-background);
      border: 1px solid var(--divider-color);
    }
    .colour-control {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    .motion-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .motion {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 10px;
      padding: 9px 10px;
      font: inherit;
      cursor: pointer;
    }
    .motion:hover {
      border-color: var(--primary-color);
    }
    .motion.active {
      border-color: var(--primary-color);
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .motion:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    .range-row {
      display: grid;
      grid-template-columns: minmax(80px, auto) minmax(120px, 1fr) 4ch;
      align-items: center;
      gap: 10px;
      color: var(--primary-text-color);
    }
    .range-row input[type="range"] {
      width: 100%;
      accent-color: var(--primary-color);
    }
    .range-row output {
      text-align: right;
      color: var(--secondary-text-color);
      font-variant-numeric: tabular-nums;
    }
    .preview-badge {
      color: var(--secondary-text-color);
      font-size: 0.78em;
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      padding: 2px 7px;
    }
    .family-grid,
    .variant-grid {
      display: flex;
      gap: 7px;
      flex-wrap: wrap;
    }
    .family,
    .variant {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 16px;
      padding: 7px 12px;
      font: inherit;
      cursor: pointer;
    }
    .family:hover,
    .variant:hover {
      border-color: var(--primary-color);
    }
    .family.active,
    .variant.active {
      border-color: var(--primary-color);
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .family:focus-visible,
    .variant:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    .palette-editor {
      display: flex;
      align-items: stretch;
      gap: 8px;
      flex-wrap: wrap;
    }
    .palette-chip {
      display: grid;
      grid-template-columns: auto auto auto;
      align-items: center;
      gap: 4px;
      padding: 5px;
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      background: var(--secondary-background-color);
    }
    .palette-chip input[type="color"] {
      grid-column: 1 / -1;
      width: 100%;
    }
    .palette-number {
      color: var(--secondary-text-color);
      font-size: 0.8em;
      font-variant-numeric: tabular-nums;
    }
    .palette-chip .btn.danger {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .palette-add {
      min-height: 76px;
      border-style: dashed;
    }
    .combo-chain {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .combo-step {
      display: grid;
      grid-template-columns: auto minmax(100px, 1fr) minmax(120px, 1fr);
      align-items: center;
      gap: 8px;
      padding: 8px;
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      background: var(--secondary-background-color);
    }
    .combo-number {
      color: var(--secondary-text-color);
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }
    .combo-step select {
      width: 100%;
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      padding: 7px 9px;
      font: inherit;
    }
    .combo-step select:focus-visible {
      outline: none;
      border-color: var(--primary-color);
      box-shadow: 0 0 0 1px var(--primary-color);
    }
    .combo-actions {
      display: flex;
      gap: 4px;
      grid-column: 2 / -1;
      justify-content: flex-end;
    }
    .combo-actions .btn.danger {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    /* Studio: "coming next" caption row of disabled kinds */
    .kinds-soon {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    /* Scope band: does this workspace touch the strip? */
    .scope-band {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      border-radius: 8px;
      font-size: 0.85em;
      font-weight: 600;
      background: var(--secondary-background-color);
    }
    .scope-band.live {
      border-left: 3px solid var(--primary-color);
      color: var(--primary-text-color);
    }
    .scope-band.draft {
      border-left: 3px solid var(--secondary-text-color);
      color: var(--secondary-text-color);
    }
    .scope-band .dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      flex: 0 0 auto;
    }
    .scope-band.live .dot {
      background: var(--primary-color);
    }
    .scope-band.draft .dot {
      border: 2px solid var(--secondary-text-color);
    }
    /* Horizontal scroll guard for the 15-cell strip on narrow cards */
    .strip-scroll {
      position: relative;
      overflow-x: auto;
    }
    .strip-scroll .strip {
      min-width: 336px;
    }
    .strip-scroll::after {
      content: "›";
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      width: 34px;
      pointer-events: none;
      display: flex;
      align-items: center;
      justify-content: flex-end;
      padding-right: 3px;
      box-sizing: border-box;
      color: var(--primary-color);
      font-size: 24px;
      font-weight: 700;
      background: linear-gradient(
        to left,
        var(--card-background-color) 35%,
        transparent
      );
      opacity: 0;
      transition: opacity 0.15s ease;
    }
    .strip-scroll.clipped::after {
      opacity: 1;
    }
    /* Non-interactive resolved preview strip */
    .strip.preview-strip {
      pointer-events: none;
    }
    /* Gradient track padding so end handles never clip */
    .gradient-track {
      padding: 0 12px;
    }
    /* Library: active row + inline delete confirm */
    .effect .badge-active {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      border-radius: 18px;
      padding: 6px 14px;
      font: inherit;
      font-weight: 600;
      background: transparent;
      color: var(--primary-color);
      border: 1px solid var(--primary-color);
      cursor: default;
    }
    .effect.active {
      border-left: 3px solid var(--primary-color);
      padding-left: 8px;
      border-radius: 4px;
    }
    .effect.quarantined {
      border-left: 3px solid var(--warning-color, #f9a825);
      padding-left: 8px;
      border-radius: 4px;
    }
    .badge-unavailable {
      display: inline-flex;
      align-items: center;
      border-radius: 18px;
      padding: 6px 10px;
      color: var(--warning-color, #f9a825);
      border: 1px solid var(--warning-color, #f9a825);
      font-size: 0.85em;
      font-weight: 600;
    }
    .effect .btn.danger {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .effect .btn.danger.primary {
      background: var(--error-color);
      color: var(--text-primary-color, #fff);
    }
    .effect .confirm-text {
      flex: 1 1 auto;
      min-width: 0;
      color: var(--primary-text-color);
      font-size: 0.9em;
    }
    @media (max-width: 360px) {
      .cell .cell-num {
        display: none;
      }
      .motion-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .range-row {
        grid-template-columns: 1fr 4ch;
      }
      .range-row > span {
        grid-column: 1 / -1;
      }
    }
`;class Tw extends W{static properties={hass:{attribute:!1},_config:{state:!0}};setConfig(w){this._config={...w}}render(){return m`
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
    `}_entityChanged(w){let r=w.detail?.value??"",u={...this._config,entity:r};this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:u},bubbles:!0,composed:!0}))}static styles=e`
    .editor {
      padding: 8px;
    }
    .help {
      margin: 8px 0 0;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
  `}customElements.define("govee-led-ble-card-editor",Tw);var cw=[{id:"fade",label:"Fade",family:0,palette_max:8,control_label:"Speed",description:"Uses a Govee Fade pattern with the shared palette.",variants:[{id:"fade-1",label:"Fade 1",variant:0},{id:"fade-2",label:"Fade 2",variant:1},{id:"fade-3",label:"Fade 3",variant:2}]},{id:"jumping",label:"Jumping",family:1,palette_max:8,control_label:"Speed",description:"Uses a Govee Jumping pattern with the shared palette.",variants:[{id:"jumping-1",label:"Jumping 1",variant:0},{id:"jumping-2",label:"Jumping 2",variant:2}]},{id:"twinkle",label:"Twinkle",family:2,palette_max:8,control_label:"Speed",description:"Uses a Govee Twinkle pattern with the shared palette.",variants:[{id:"twinkle-1",label:"Twinkle 1",variant:0},{id:"twinkle-2",label:"Twinkle 2",variant:1},{id:"twinkle-3",label:"Twinkle 3",variant:2}]},{id:"marquee",label:"Marquee",family:3,palette_max:8,control_label:"Speed",description:"Uses a Govee Marquee pattern with the shared palette.",variants:[{id:"marquee-1",label:"Marquee 1",variant:3},{id:"marquee-2",label:"Marquee 2",variant:4},{id:"marquee-3",label:"Marquee 3",variant:5}]},{id:"music",label:"Music",family:4,palette_max:8,control_label:"Sensitivity",description:"Uses a Govee DIY Music pattern, separate from the light's Music mode.",variants:[{id:"music-1",label:"Music 1",variant:8},{id:"music-2",label:"Music 2",variant:6},{id:"music-3",label:"Music 3",variant:7}]},{id:"chasing",label:"Chasing",family:8,palette_max:8,control_label:"Speed",description:"Uses a Govee Chasing pattern with the shared palette.",variants:[{id:"chasing-1",label:"Chasing 1",variant:9},{id:"chasing-2",label:"Chasing 2",variant:10}]},{id:"rainbow",label:"Rainbow",family:9,palette_max:8,control_label:"Speed",description:"Uses a Govee Rainbow pattern with the shared palette.",variants:[{id:"rainbow-1",label:"Rainbow 1",variant:9},{id:"rainbow-2",label:"Rainbow 2",variant:10}]},{id:"crossing",label:"Crossing",family:10,palette_max:3,control_label:"Speed",description:"Uses the single Govee Crossing pattern with up to three colours.",variants:[{id:"crossing",label:"Crossing",variant:0}]}];var Z=cw,ww=[{code:2,label:"Cycle"},{code:9,label:"Clockwise"},{code:10,label:"Counter-clockwise"},{code:15,label:"Twinkle"},{code:19,label:"Gradient"},{code:20,label:"Breathe"}];function X(w,r){if(w===null||typeof w!=="object"||Array.isArray(w))throw Error(`${r} must be an object.`);return w}function a(w,r){if(typeof w!=="string"||w.trim()==="")throw Error(`${r} must be a non-empty string.`);return w.trim()}function k(w,r){if(typeof w!=="number"||!Number.isInteger(w))throw Error(`${r} must be an integer.`);return w}function c(w,r){let u=k(w,r);if(u<0||u>100)throw Error(`${r} must be from 0 to 100.`);return u}function Ur(w,r){let u=k(w,r);if(u<0||u>255)throw Error(`${r} must be from 0 to 255.`);return u}function U(w,r){if(!Array.isArray(w))throw Error(`${r} must be an array.`);return w}function zw(w,r){let u=U(w,r);if(u.length!==3||u.some((o)=>typeof o!=="number"||!Number.isInteger(o)||o<0||o>255))throw Error(`${r} must contain three channels from 0 to 255.`);return[u[0],u[1],u[2]]}function Ar(w,r){return w===null?null:zw(w,r)}function qw(w,r){return U(w,r).map((u,o)=>zw(u,`${r}[${o}]`))}function iw(w,r){return U(w,r).map((u,o)=>Ar(u,`${r}[${o}]`))}function xw(w){let r=X(w,"Effect content"),u=a(r.kind,"Effect kind");switch(u){case"segments":{let o=r.brightness,$=null;if(o!==null)$=U(o,"Segment brightness").map((b,p)=>b===null?null:c(b,`Segment brightness[${p}]`));return{kind:u,colors:iw(r.colors,"Segment colours"),brightness:$}}case"vibrant":{let o=qw(r.stops,"Gradient stops");if(o.length<2||o.length>5)throw Error("Gradient stops must contain from 2 to 5 colours.");return{kind:u,stops:o}}case"sketch":{let o=k(r.motion,"Sketch motion");if(!ww.some(($)=>$.code===o))throw Error("Sketch motion is not supported.");return{kind:u,motion:o,speed:c(r.speed,"Sketch speed"),brightness:c(r.brightness,"Sketch brightness"),background:zw(r.background,"Sketch background"),colors:iw(r.colors,"Sketch colours")}}case"flat":{let o=k(r.family,"Flat family"),$=k(r.variant,"Flat variant");A(o,$);let b=qw(r.palette,"Flat palette"),p=V(o);if(b.length>p.palette_max)throw Error(`${p.label} accepts up to ${p.palette_max} colours.`);return{kind:u,family:o,variant:$,speed:c(r.speed,"Flat speed"),palette:b}}case"combo":{let o=U(r.effects,"Combo effects").map((b,p)=>{let n=U(b,`Combo effects[${p}]`);if(n.length!==2)throw Error(`Combo effects[${p}] must contain a family and variant.`);let E=k(n[0],`Combo effects[${p}].family`),q=k(n[1],`Combo effects[${p}].variant`);return A(E,q),[E,q]});if(o.length>4)throw Error("Combo accepts up to four steps.");let $=qw(r.palette,"Combo palette");if($.length>8)throw Error("Combo accepts up to 8 colours.");return{kind:u,variant:Ur(r.variant,"Combo variant"),speed:c(r.speed,"Combo speed"),palette:$,effects:o}}default:throw Error(`Unsupported effect kind "${u}".`)}}function sw(w){let r=X(w,"Export response"),u=k(r.segment_count,"Export segment count");if(u<=0)throw Error("Export segment count must be positive.");return{id:a(r.id,"Effect ID"),name:a(r.name,"Effect name"),model:a(r.model,"Effect model"),segment_count:u,content:X(r.content,"Effect content")}}function Ir(w){let r=sw(w);return{...r,content:xw(r.content)}}function jw(w,r){let u=X(w,"Entity service response");if(!(r in u))throw Error(`The export response did not include ${r}.`);return Ir(u[r])}function ew(w,r){let u=X(w,"Entity service response");if(!(r in u))throw Error(`The export response did not include ${r}.`);return sw(u[r])}function tw(w){return{schema_version:1,integration:"ha_govee_led_ble",source:{model:w.model,segment_count:w.segment_count},effect:{name:w.name,content:w.content}}}function wr(w,r){let u;try{u=JSON.parse(w)}catch{throw Error("This is not valid JSON.")}let o=X(u,"Effect document");if(o.schema_version!==1)throw Error("This effect uses an unsupported schema version.");if(o.integration!=="ha_govee_led_ble")throw Error("This file is not a Govee LED BLE effect.");let $=X(o.source,"Effect source"),b=a($.model,"Source model"),p=k($.segment_count,"Source segment count");if(p<=0)throw Error("Source segment count must be positive.");if(p!==r.segmentCount)throw Error(`This effect needs ${p} segments; this light has ${r.segmentCount}.`);if(r.model!==null&&r.model!==b)throw Error(`This effect was exported for ${b}; this light is ${r.model}.`);let n=X(o.effect,"Effect"),E=xw(n.content);if((E.kind==="segments"||E.kind==="sketch")&&E.colors.length>p)throw Error(`This effect contains more than ${p} segments.`);if(E.kind==="segments"&&E.brightness!==null&&E.brightness.length>p)throw Error(`This effect contains more than ${p} brightness values.`);return{schema_version:1,integration:"ha_govee_led_ble",source:{model:b,segment_count:p},effect:{name:a(n.name,"Effect name"),content:E}}}function Zw(w){switch(w.kind){case"segments":return"static";case"vibrant":return"gradient";default:return w.kind}}function Qw(w,r,u,o,$){return{kind:"sketch",motion:r,speed:u,brightness:o,background:[$[0],$[1],$[2]],colors:w.map((b)=>b===null?null:[b[0],b[1],b[2]])}}function V(w){let r=Z.find((u)=>u.family===w);if(r===void 0)throw Error(`Unknown Flat family ${w}.`);return r}function rr(w,r,u,o){let $=V(w);if(!$.variants.some((b)=>b.variant===r))throw Error(`Unknown variant for ${$.label}.`);if(o.length===0)throw Error("Add at least one palette colour.");if(o.length>$.palette_max)throw Error(`${$.label} accepts up to ${$.palette_max} colours.`);return{kind:"flat",family:w,variant:r,speed:u,palette:o.map((b)=>[b[0],b[1],b[2]])}}function A(w,r){let u=V(w),o=u.variants.find(($)=>$.variant===r);if(o===void 0)throw Error(`Unknown variant for ${u.label}.`);return o.label}function ur(w,r,u,o=0){if(!Number.isInteger(o)||o<0||o>255)throw Error("Combo variant must be from 0 to 255.");if(w.length===0)throw Error("Add at least one Combo step.");if(w.length>4)throw Error("Combo accepts up to four steps.");for(let[$,b]of w)A($,b);if(u.length===0)throw Error("Add at least one palette colour.");if(u.length>8)throw Error("Combo accepts up to 8 colours.");return{kind:"combo",variant:o,speed:r,palette:u.map(($)=>[$[0],$[1],$[2]]),effects:w.map(([$,b])=>[$,b])}}function or(w){let r=Math.max(0,Math.min(100,w.brightness))/100;return w.colors.map((u)=>{return(u??w.background).map(($)=>Math.round($*r))})}function Vw(w,r){let u=new Set(r.map(i)),o=`${$r(w)} copy`;if(!u.has(i(o)))return o;for(let $=2;;$+=1){let b=`${o} ${$}`;if(!u.has(i(b)))return b}}function $r(w){return w.trim().replace(/^["'“”‘’]+|["'“”‘’]+$/gu,"").trim().replace(/\s+/gu," ")}function i(w){return $r(w).toLocaleLowerCase().replaceAll("ß","ss").replaceAll("ς","σ")}function br(w,r){let u=w.trim();return r.some(($)=>i($)===i(u))?Vw(u,r):u}function pr(w){return`${w.trim().toLocaleLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"")||"govee-effect"}.json`}var R=15;function D(w,r,u){return Math.max(r,Math.min(u,w))}function j(w){let r=w.replace("#","");return[parseInt(r.slice(0,2),16),parseInt(r.slice(2,4),16),parseInt(r.slice(4,6),16)]}function Y(w){return"#"+w.map((r)=>D(Math.round(r),0,255).toString(16).padStart(2,"0")).join("")}function rw(w,r){if(w.length===0)throw Error("no stops");if(w.length===1){let E=w[0];return[E[0],E[1],E[2]]}let u=w.length-1,o=D(r,0,1)*u,$=D(Math.floor(o),0,u-1),b=o-$,p=w[$],n=w[$+1];return[p[0]+(n[0]-p[0])*b,p[1]+(n[1]-p[1])*b,p[2]+(n[2]-p[2])*b]}function lr(w){let r=Math.floor(w),u=w-r;if(u<0.5)return r;if(u>0.5)return r+1;return r%2===0?r:r+1}function uw(w,r=15){if(w.length===0)throw Error("no stops");if(r<=0)return[];if(w.length===1){let u=w[0];return Array.from({length:r},()=>[u[0],u[1],u[2]])}return Array.from({length:r},(u,o)=>{let $=r>1?o/(r-1):0;return rw(w,$).map(lr)})}function Fw(w){let r=new Map,u=[];return w.forEach((o,$)=>{let b=`${o[0]},${o[1]},${o[2]}`,p=r.get(b);if(p===void 0)p={segments:[],rgb_color:[o[0],o[1],o[2]]},r.set(b,p),u.push(p);p.segments.push($+1)}),u}var mr=[{id:"sunset",name:"Sunset",stops:[[255,89,94],[255,146,76],[255,202,58]]},{id:"ocean",name:"Ocean",stops:[[15,32,89],[25,130,196],[112,193,179]]},{id:"forest",name:"Forest",stops:[[27,67,50],[45,106,79],[149,213,178]]},{id:"rainbow",name:"Rainbow",stops:[[255,0,0],[255,183,0],[0,200,83],[0,145,234],[170,0,255]]},{id:"warm-white",name:"Warm white",stops:[[255,183,107]]},{id:"cool-white",name:"Cool white",stops:[[188,220,255]]}];function Er(w,r=15){return Fw(uw(w.stops,r))}function nr(w){return[...new Set(w)].sort((r,u)=>r-u)}function Br(w,r){let u=Math.min(w,r),o=Math.max(w,r),$=new Set;for(let b=u;b<=o;b++)$.add(b);return $}function Dw(w,r){let u=new Set(w);if(u.has(r))u.delete(r);else u.add(r);return u}function Jr(w=15){let r=new Set;for(let u=1;u<=w;u++)r.add(u);return r}function G(){return new Set}function ow(w){if(w===null||typeof w!=="object"||Array.isArray(w))return[];let r=[];for(let[u,o]of Object.entries(w)){if(typeof o!=="string")continue;let $=o.trim();if($==="")continue;r.push({id:u,name:$})}return r.sort((u,o)=>{let $=u.name.toLowerCase(),b=o.name.toLowerCase();if($!==b)return $<b?-1:1;if(u.id!==o.id)return u.id<o.id?-1:1;return 0}),r}var I=[{id:"now",label:"Now"},{id:"studio",label:"Studio"},{id:"library",label:"Library"}];function l(w,r,u){if(u<=0)return w;switch(r){case"ArrowRight":case"ArrowDown":return(w+1)%u;case"ArrowLeft":case"ArrowUp":return(w-1+u)%u;case"Home":return 0;case"End":return u-1;default:return w}}var y=[{id:"static",label:"Static",available:!0},{id:"gradient",label:"Gradient",available:!0},{id:"sketch",label:"Sketch",available:!0},{id:"flat",label:"Flat",available:!0},{id:"combo",label:"Combo",available:!0}],yr={static:"segments",gradient:"vibrant",sketch:"sketch",flat:"flat",combo:"combo"};function Rr(w){let r=y.filter((o)=>o.available);if(!Array.isArray(w))return r.map((o)=>o.id);let u=new Set(w.filter((o)=>typeof o==="string"));return r.filter((o)=>u.has(yr[o.id])).map((o)=>o.id)}function qr(w,r=null){let u=r!==null&&r.some((o)=>o!==null);return{kind:"segments",colors:w.map((o)=>o===null?null:[o[0],o[1],o[2]]),brightness:u?r.map((o)=>o===null?null:o):null}}function zr(w,r=null){return w.some((u)=>u!==null)||r!==null&&r.some((u)=>u!==null)}function jr(w){return{kind:"vibrant",stops:w.map((r)=>[r[0],r[1],r[2]])}}function Yw(w){if(w!==null&&typeof w==="object"){let r=w.message;if(typeof r==="string"&&r.trim()!=="")return r}return null}function F(w,r="Something went wrong."){if(typeof w==="string"&&w.trim()!=="")return w;let u=Yw(w);if(u!==null)return u;if(w!==null&&typeof w==="object"){let o=w,$=Yw(o.error)??Yw(o.body);if($!==null)return $}return r}var K=["#ff595e","#ffca3a","#1982c4"],Ww="#33cc66",kw=2,Cw=5,Zr="Govee Effect Studio",Qr=y.filter((w)=>!w.available);function Or(w){if(!Array.isArray(w))return null;let r=[];for(let u of w){if(!Array.isArray(u)||u.length<3)return null;let[o,$,b]=u;if(typeof o!=="number"||typeof $!=="number"||typeof b!=="number")return null;r.push([o,$,b])}return r}function Nr(w,r){let u=window.document.createElement("a");return u.download=w,u.href=r,u}class Vr extends W{static properties={hass:{attribute:!1},_config:{state:!0},_tab:{state:!0},_studioKind:{state:!0},_selection:{state:!0},_cursor:{state:!0},_paintColor:{state:!0},_staticColors:{state:!0},_staticBrightness:{state:!0},_sketchColors:{state:!0},_sketchMotion:{state:!0},_sketchSpeed:{state:!0},_sketchBrightness:{state:!0},_sketchBackground:{state:!0},_flatFamily:{state:!0},_flatVariant:{state:!0},_flatSpeed:{state:!0},_flatPalette:{state:!0},_comboEffects:{state:!0},_comboVariant:{state:!0},_comboSpeed:{state:!0},_comboPalette:{state:!0},_stops:{state:!0},_studioStops:{state:!0},_dragStop:{state:!0},_dragFrac:{state:!0},_effectName:{state:!0},_studioName:{state:!0},_editingId:{state:!0},_loadedContent:{state:!0},_pendingDraft:{state:!0},_importText:{state:!0},_busyKey:{state:!0},_renamingId:{state:!0},_renameValue:{state:!0},_deletingId:{state:!0},_feedback:{state:!0}};_dragging=!1;_dragAnchor=1;_touchStart=null;_ro;_draftBaseline="";_editingOriginalName=null;_editingOriginalContent=null;constructor(){super();this._tab="now",this._studioKind="static",this._selection=new Set,this._cursor=1,this._paintColor=Ww,this._staticColors=Array.from({length:R},()=>null),this._staticBrightness=null,this._sketchColors=Array.from({length:R},()=>null),this._sketchMotion=9,this._sketchSpeed=51,this._sketchBrightness=100,this._sketchBackground="#000000",this._flatFamily=Z[0].family,this._flatVariant=Z[0].variants[0].variant,this._flatSpeed=50,this._flatPalette=[...K],this._comboEffects=[{family:Z[0].family,variant:Z[0].variants[0].variant}],this._comboVariant=0,this._comboSpeed=50,this._comboPalette=[...K],this._stops=[...K],this._studioStops=[...K],this._dragStop=null,this._dragFrac=null,this._effectName="",this._studioName="",this._editingId=null,this._loadedContent=null,this._pendingDraft=null,this._importText="",this._busyKey=null,this._renamingId=null,this._renameValue="",this._deletingId=null,this._feedback=null,this._draftBaseline=this._draftSignature()}static getStubConfig(w){return{entity:(w?Object.keys(w.states).find((u)=>u.startsWith("light.")&&Array.isArray(w.states[u].attributes?.segment_colors)):void 0)??""}}static getConfigElement(){return document.createElement("govee-led-ble-card-editor")}setConfig(w){if(!w)throw Error("Invalid configuration");this._config={...w}}getCardSize(){return 12}connectedCallback(){super.connectedCallback(),this._ro=new ResizeObserver(()=>{this._updateClipped(),this._drawNowPreview()}),this._ro.observe(this)}disconnectedCallback(){super.disconnectedCallback(),this._ro?.disconnect(),window.removeEventListener("pointermove",this._onMove),window.removeEventListener("pointerup",this._onUp),window.removeEventListener("pointercancel",this._onUp),window.removeEventListener("pointerup",this._onTouchUp),window.removeEventListener("pointercancel",this._onTouchCancel),window.removeEventListener("pointermove",this._onStopMove),window.removeEventListener("pointerup",this._onStopUp)}updated(){this._ensureSupportedStudioKind(),this._reconcileDraftIds(),this._updateClipped(),this._drawNowPreview()}_reconcileDraftIds(){let w=this._config?.entity,r=w?this.hass?.states[w]:void 0;if(!r)return;let u=ow(r.attributes?.custom_effects),o=new Set(u.map(($)=>$.id));if(this._editingId!==null){let $=u.find((b)=>b.id===this._editingId);if($===void 0)this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._draftBaseline="",this._feedback={kind:"info",text:"The saved effect was removed elsewhere. Its Studio draft is now a new effect."};else if(this._editingOriginalName!==null&&this._studioName.trim()===this._editingOriginalName&&$.name!==this._editingOriginalName){let b=this._currentContentSignature()===this._editingOriginalContent;if(this._studioName=$.name,this._editingOriginalName=$.name,b)this._draftBaseline=this._draftSignature()}}if(this._pendingDraft?.editingId!==null&&this._pendingDraft?.editingId!==void 0&&!o.has(this._pendingDraft.editingId))this._pendingDraft={...this._pendingDraft,editingId:null,feedback:"The saved effect was removed elsewhere. Its loaded content will open as a new draft."}}_updateClipped(){for(let w of this.renderRoot.querySelectorAll(".strip-scroll"))w.classList.toggle("clipped",w.scrollWidth>w.clientWidth+1)}_selectTab(w){if(this._tab===w)return;this._tab=w,this._selection=G(),this._cursor=1}_onTabKey(w){let r=I.findIndex((o)=>o.id===this._tab),u=l(r,w.key,I.length);if(u===r)return;w.preventDefault(),this._selectTab(I[u].id),this.updateComplete.then(()=>{this.renderRoot.querySelector(`#tab-${I[u].id}`)?.focus()})}_draftSignature(){let w={kind:this._studioKind,name:this._studioName};switch(this._studioKind){case"static":return JSON.stringify({...w,colors:this._staticColors,brightness:this._staticBrightness});case"gradient":return JSON.stringify({...w,stops:this._studioStops});case"sketch":return JSON.stringify({...w,colors:this._sketchColors,motion:this._sketchMotion,speed:this._sketchSpeed,brightness:this._sketchBrightness,background:this._sketchBackground});case"flat":return JSON.stringify({...w,family:this._flatFamily,variant:this._flatVariant,speed:this._flatSpeed,palette:this._flatPalette});case"combo":return JSON.stringify({...w,effects:this._comboEffects,variant:this._comboVariant,speed:this._comboSpeed,palette:this._comboPalette})}}_hasUnsavedDraft(){return this._draftSignature()!==this._draftBaseline}_selectKind(w){if(!this._supportedStudioKinds().includes(w))return;if(this._editingId!==null&&w!==this._studioKind)return;let r=this._hasUnsavedDraft();if(this._studioKind=w,this._loadedContent=null,!r&&this._editingId===null)this._draftBaseline=this._draftSignature()}_onKindKey(w){if(this._editingId!==null)return;let r=this._availableKindDescriptors(),u=r.findIndex(($)=>$.id===this._studioKind),o=l(u,w.key,r.length);if(o===u)return;w.preventDefault(),this._selectKind(r[o].id),this.updateComplete.then(()=>{this.renderRoot.querySelector('.kinds .kind[aria-checked="true"]')?.focus()})}_focusChecked(w){this.updateComplete.then(()=>{this.renderRoot.querySelector(`${w}[aria-checked="true"]`)?.focus()})}_onMotionKey(w){let r=ww.map(($)=>$.code),u=r.indexOf(this._sketchMotion),o=l(u,w.key,r.length);if(o===u)return;w.preventDefault(),this._sketchMotion=r[o],this._focusChecked(".motion")}_onFlatFamilyKey(w){let r=Z.map(($)=>$.family),u=r.indexOf(this._flatFamily),o=l(u,w.key,r.length);if(o===u)return;w.preventDefault(),this._selectFlatFamily(r[o]),this._focusChecked(".family")}_onFlatVariantKey(w){let r=V(this._flatFamily).variants.map(($)=>$.variant),u=r.indexOf(this._flatVariant),o=l(u,w.key,r.length);if(o===u)return;w.preventDefault(),this._flatVariant=r[o],this._focusChecked(".variant")}_segmentColors(){let w=this._config?.entity;if(!w||!this.hass)return null;let r=this.hass.states[w];if(!r)return null;return Or(r.attributes?.segment_colors)}_supportedStudioKinds(){let w=this._config?.entity,r=w?this.hass?.states[w]?.attributes?.custom_effect_kinds:void 0;return Rr(r)}_availableKindDescriptors(){let w=new Set(this._supportedStudioKinds());return y.filter((r)=>r.available&&w.has(r.id))}_isStudioKindSupported(w){return this._supportedStudioKinds().includes(w)}_ensureSupportedStudioKind(){if(this._isStudioKindSupported(this._studioKind))return;let[w]=this._supportedStudioKinds();if(w===void 0)return;this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._loadedContent=null,this._studioKind=w,this._draftBaseline=this._draftSignature()}_cellFromClientX(w){let r=this.renderRoot.querySelector(".strip");if(!r)return 1;let u=r.getBoundingClientRect(),o=u.width/R;return D(Math.floor((w-u.left)/o),0,R-1)+1}_onDown(w){if(w.pointerType==="touch"){this._touchStart={x:w.clientX,y:w.clientY,cell:this._cellFromClientX(w.clientX)},window.addEventListener("pointerup",this._onTouchUp),window.addEventListener("pointercancel",this._onTouchCancel);return}w.preventDefault(),this._dragging=!0,this._dragAnchor=this._cellFromClientX(w.clientX),this._cursor=this._dragAnchor,this._selection=new Set([this._dragAnchor]),this.renderRoot.querySelector(".strip")?.focus(),window.addEventListener("pointermove",this._onMove),window.addEventListener("pointerup",this._onUp),window.addEventListener("pointercancel",this._onUp)}_onMove=(w)=>{if(!this._dragging)return;let r=this._cellFromClientX(w.clientX);this._selection=Br(this._dragAnchor,r),this._cursor=r};_onUp=()=>{this._dragging=!1,window.removeEventListener("pointermove",this._onMove),window.removeEventListener("pointerup",this._onUp),window.removeEventListener("pointercancel",this._onUp)};_onTouchUp=(w)=>{let r=this._touchStart;if(this._clearTouchGesture(),r===null||Math.hypot(w.clientX-r.x,w.clientY-r.y)>10)return;this._cursor=r.cell,this._selection=Dw(this._selection,r.cell)};_onTouchCancel=()=>{this._clearTouchGesture()};_clearTouchGesture(){this._touchStart=null,window.removeEventListener("pointerup",this._onTouchUp),window.removeEventListener("pointercancel",this._onTouchCancel)}_onKey(w){let r=w.key,u=["ArrowRight","ArrowDown","ArrowLeft","ArrowUp","Home","End"];if(r==="ArrowRight"||r==="ArrowDown")this._cursor=D(this._cursor+1,1,R),w.preventDefault();else if(r==="ArrowLeft"||r==="ArrowUp")this._cursor=D(this._cursor-1,1,R),w.preventDefault();else if(r==="Home")this._cursor=1,w.preventDefault();else if(r==="End")this._cursor=R,w.preventDefault();else if(r===" "||r==="Spacebar")this._selection=Dw(this._selection,this._cursor),w.preventDefault();else if(r==="Enter"){if(this._tab==="studio")this._paintActiveDraft();else this._applyPaint();w.preventDefault()}else if(r==="Escape")this._dragging=!1,this._selection=G(),w.preventDefault();if(u.includes(r))this._scrollCursorIntoView()}_scrollCursorIntoView(){this.updateComplete.then(()=>{this.renderRoot.querySelector(".cell.cursor")?.scrollIntoView({inline:"nearest",block:"nearest"})})}_selectAll(){this._selection=Jr(R)}_clear(){this._selection=G()}_applyPaint(){let w=this._config?.entity;if(!this.hass||!w||this._selection.size===0)return;let r=[{segments:nr(this._selection),rgb_color:j(this._paintColor)}];this.hass.callService("ha_govee_led_ble","paint_segments",{groups:r},{entity_id:w})}_paintStatic(){if(this._selection.size===0)return;let w=[...this._staticColors];for(let r of this._selection)w[r-1]=this._paintColor;this._staticColors=w}_paintSketch(){if(this._selection.size===0)return;let w=[...this._sketchColors];for(let r of this._selection)w[r-1]=this._paintColor;this._sketchColors=w}_paintActiveDraft(){if(this._studioKind==="sketch")this._paintSketch();else this._paintStatic()}_setUnchangedStatic(){if(this._selection.size===0)return;let w=[...this._staticColors];for(let r of this._selection)w[r-1]=null;this._staticColors=w}_clearSketchSelection(){if(this._selection.size===0)return;let w=[...this._sketchColors];for(let r of this._selection)w[r-1]=null;this._sketchColors=w}_resetStatic(){this._staticColors=Array.from({length:R},()=>null),this._staticBrightness=null,this._selection=G(),this._finishDraftReset()}_resetSketch(){this._sketchColors=Array.from({length:R},()=>null),this._sketchMotion=9,this._sketchSpeed=51,this._sketchBrightness=100,this._sketchBackground="#000000",this._selection=G(),this._finishDraftReset()}_selectFlatFamily(w){let r=V(w);if(this._flatPalette.length>r.palette_max){this._feedback={kind:"error",text:`${r.label} accepts up to ${r.palette_max} colours. Remove some first.`};return}this._flatFamily=w,this._flatVariant=r.variants[0].variant,this._feedback=null}_setFlatPaletteColour(w,r){let u=[...this._flatPalette];u[w]=r,this._flatPalette=u}_addFlatPaletteColour(){let w=V(this._flatFamily).palette_max;if(this._flatPalette.length>=w)return;this._flatPalette=[...this._flatPalette,Ww]}_removeFlatPaletteColour(w){this._flatPalette=this._flatPalette.filter((r,u)=>u!==w)}_moveFlatPaletteColour(w,r){let u=w+r;if(u<0||u>=this._flatPalette.length)return;let o=[...this._flatPalette];[o[w],o[u]]=[o[u],o[w]],this._flatPalette=o}_resetFlat(){this._flatFamily=Z[0].family,this._flatVariant=Z[0].variants[0].variant,this._flatSpeed=50,this._flatPalette=[...K],this._finishDraftReset()}_setComboFamily(w,r){let u=V(r);this._comboEffects=this._comboEffects.map((o,$)=>$===w?{family:r,variant:u.variants[0].variant}:o)}_setComboVariant(w,r){let u=this._comboEffects[w];A(u.family,r),this._comboEffects=this._comboEffects.map((o,$)=>$===w?{...o,variant:r}:o)}_addComboStep(){if(this._comboEffects.length>=4)return;let w=Z[0];this._comboEffects=[...this._comboEffects,{family:w.family,variant:w.variants[0].variant}]}_removeComboStep(w){this._comboEffects=this._comboEffects.filter((r,u)=>u!==w)}_moveComboStep(w,r){let u=w+r;if(u<0||u>=this._comboEffects.length)return;let o=[...this._comboEffects];[o[w],o[u]]=[o[u],o[w]],this._comboEffects=o}_setComboPaletteColour(w,r){let u=[...this._comboPalette];u[w]=r,this._comboPalette=u}_addComboPaletteColour(){if(this._comboPalette.length>=8)return;this._comboPalette=[...this._comboPalette,Ww]}_removeComboPaletteColour(w){this._comboPalette=this._comboPalette.filter((r,u)=>u!==w)}_moveComboPaletteColour(w,r){let u=w+r;if(u<0||u>=this._comboPalette.length)return;let o=[...this._comboPalette];[o[w],o[u]]=[o[u],o[w]],this._comboPalette=o}_resetCombo(){let w=Z[0];this._comboEffects=[{family:w.family,variant:w.variants[0].variant}],this._comboVariant=0,this._comboSpeed=50,this._comboPalette=[...K],this._finishDraftReset()}_finishDraftReset(){if(this._editingId===null)this._draftBaseline=this._draftSignature()}_activeStops(){return this._tab==="studio"?this._studioStops:this._stops}_setActiveStops(w){if(this._tab==="studio")this._studioStops=w;else this._stops=w}_addStop(){let w=this._activeStops();if(w.length>=Cw)return;let r=rw(w.map(j),0.5);this._setActiveStops([...w,Y(r)])}_removeStop(w){let r=this._activeStops();if(r.length<=kw)return;this._setActiveStops(r.filter((u,o)=>o!==w))}_moveStop(w,r){let u=w+r,o=this._activeStops();if(u<0||u>=o.length)return;let $=[...o];[$[w],$[u]]=[$[u],$[w]],this._setActiveStops($)}_recolourStop(w,r){let u=[...this._activeStops()];u[w]=r,this._setActiveStops(u)}_stopTargetIndex(w){let r=this.renderRoot.querySelector(".gradient-bar"),u=this._activeStops();if(!r)return this._dragStop??0;let o=r.getBoundingClientRect(),$=D((w-o.left)/o.width,0,1);return D(Math.round($*(u.length-1)),0,u.length-1)}_startStopDrag(w,r){w.preventDefault(),this._dragStop=r,window.addEventListener("pointermove",this._onStopMove),window.addEventListener("pointerup",this._onStopUp)}_onStopMove=(w)=>{if(this._dragStop===null)return;let r=this.renderRoot.querySelector(".gradient-bar");if(!r)return;let u=r.getBoundingClientRect();this._dragFrac=D((w.clientX-u.left)/u.width,0,1)};_onStopUp=(w)=>{if(this._dragStop===null)return;let r=this._dragStop,u=this._stopTargetIndex(w.clientX);if(r!==u){let o=[...this._activeStops()],[$]=o.splice(r,1);o.splice(u,0,$),this._setActiveStops(o)}this._dragStop=null,this._dragFrac=null,window.removeEventListener("pointermove",this._onStopMove),window.removeEventListener("pointerup",this._onStopUp)};_applyGradient(){let w=this._config?.entity;if(!this.hass||!w)return;let r=Fw(uw(this._stops.map(j),R));this.hass.callService("ha_govee_led_ble","paint_segments",{groups:r},{entity_id:w})}_applyPreset(w){let r=this._config?.entity;if(!this.hass||!r)return;this.hass.callService("ha_govee_led_ble","paint_segments",{groups:Er(w)},{entity_id:r})}_presetSwatch(w){if(w.length===1){let[u,o,$]=w[0];return`rgb(${u},${o},${$})`}return`linear-gradient(90deg, ${w.map(([u,o,$],b)=>`rgb(${u},${o},${$}) ${b/(w.length-1)*100}%`).join(", ")})`}async _saveCurrent(){let w=this._config?.entity;if(!this.hass||!w)return;let r=this._effectName.trim();try{await this.hass.callService("ha_govee_led_ble","save_effect",{name:r,capture_current:!0},{entity_id:w}),this._effectName="",this._feedback={kind:"info",text:`Saved "${r}".`}}catch(u){this._feedback={kind:"error",text:F(u)}}}_currentStudioContent(){if(this._studioKind==="static")return qr(this._staticColors.map((w)=>w===null?null:j(w)),this._staticBrightness);if(this._studioKind==="gradient")return jr(this._studioStops.map(j));if(this._studioKind==="sketch")return Qw(this._sketchColors.map((w)=>w===null?null:j(w)),this._sketchMotion,this._sketchSpeed,this._sketchBrightness,j(this._sketchBackground));if(this._studioKind==="flat")return rr(this._flatFamily,this._flatVariant,this._flatSpeed,this._flatPalette.map(j));if(this._studioKind==="combo")return ur(this._comboEffects.map((w)=>[w.family,w.variant]),this._comboSpeed,this._comboPalette.map(j),this._comboVariant);throw Error(`The ${this._studioKind} editor is not available yet.`)}_currentContentSignature(){try{return JSON.stringify(this._currentStudioContent())}catch{return null}}_targetModel(){let w=this._config?.entity;if(!w||!this.hass)return null;let r=this.hass.entities?.[w]?.device_id;if(!r)return null;return this.hass.devices?.[r]?.model??null}_knownEffectNames(w){let r=this._config?.entity,u=r?this.hass?.states[r]?.attributes?.effect_list:void 0;return[...Array.isArray(u)?u.filter(($)=>typeof $==="string"):[],...w.map(($)=>$.name)]}_loadDraft(w,r,u){if(this._editingId=u,this._loadedContent=r,this._studioName=w,this._studioKind=Zw(r),this._selection=G(),this._cursor=1,r.kind==="segments")this._staticColors=Array.from({length:R},(o,$)=>{let b=r.colors[$];return b===void 0||b===null?null:Y(b)}),this._staticBrightness=r.brightness===null?null:Array.from({length:R},(o,$)=>r.brightness?.[$]??null);else if(r.kind==="vibrant")this._studioStops=r.stops.map(Y);else if(r.kind==="sketch")this._sketchColors=Array.from({length:R},(o,$)=>{let b=r.colors[$];return b===void 0||b===null?null:Y(b)}),this._sketchMotion=r.motion,this._sketchSpeed=r.speed,this._sketchBrightness=r.brightness,this._sketchBackground=Y(r.background);else if(r.kind==="flat")V(r.family),this._flatFamily=r.family,this._flatVariant=r.variant,this._flatSpeed=r.speed,this._flatPalette=r.palette.map(Y);else if(r.kind==="combo"){for(let[o,$]of r.effects)A(o,$);this._comboEffects=r.effects.map(([o,$])=>({family:o,variant:$})),this._comboVariant=r.variant,this._comboSpeed=r.speed,this._comboPalette=r.palette.map(Y)}this._tab="studio",this._pendingDraft=null,this._editingOriginalName=u===null?null:w.trim(),this._editingOriginalContent=u===null?null:JSON.stringify(r),this._draftBaseline=u===null?"":this._draftSignature()}_resetStudioDraft(){this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._loadedContent=null,this._studioName="",this._staticColors=Array.from({length:R},()=>null),this._staticBrightness=null,this._studioStops=[...K],this._resetSketch(),this._resetFlat(),this._resetCombo(),this._selection=G(),this._cursor=1,this._pendingDraft=null,this._draftBaseline=this._draftSignature()}_cancelEdit(){this._resetStudioDraft(),this._feedback={kind:"info",text:"Edit cancelled."}}_offerDraft(w,r,u,o,$=!1){let b=Zw(r);if(!this._isStudioKindSupported(b)){this._feedback={kind:"error",text:`This light does not support ${y.find((p)=>p.id===b)?.label??b} effects.`};return}if(this._hasUnsavedDraft()){this._pendingDraft={name:w,content:r,editingId:u,feedback:o,clearImport:$},this.updateComplete.then(()=>{this.renderRoot.querySelector(".keep-draft")?.focus()});return}if(this._loadDraft(w,r,u),$)this._importText="";this._feedback={kind:"info",text:o}}_confirmDraftReplacement(){let w=this._pendingDraft;if(w===null)return;if(this._loadDraft(w.name,w.content,w.editingId),w.clearImport)this._importText="";this._feedback={kind:"info",text:w.feedback}}_keepDraft(){this._pendingDraft=null,this._feedback={kind:"info",text:"Kept the existing Studio draft."}}async _saveStudio(){let w=this._config?.entity;if(!this.hass||!w)return;if(!this._isStudioKindSupported(this._studioKind)){this._feedback={kind:"error",text:"This effect type is not supported by this light."};return}let r=this._studioName.trim();try{let u=this._currentStudioContent(),o=this._editingId;if(o===null)await this.hass.callService("ha_govee_led_ble","save_effect",{name:r,content:u},{entity_id:w}),this._feedback={kind:"info",text:`Saved "${r}".`};else{let $={id:o};if(this._editingOriginalName===null||r!==this._editingOriginalName)$.name=r;if(this._editingOriginalContent===null||JSON.stringify(u)!==this._editingOriginalContent)$.content=u;if(Object.keys($).length===1){this._feedback={kind:"info",text:"No changes to update."};return}await this.hass.callService("ha_govee_led_ble","update_effect",$,{entity_id:w}),this._feedback={kind:"info",text:`Updated "${r}".`}}this._resetStudioDraft()}catch(u){this._feedback={kind:"error",text:F(u)}}}async _readEffect(w,r,u){let o=this._config?.entity;if(!this.hass||!o)throw Error("The light is unavailable.");this._busyKey=`${r}:${w.id}`;try{let $=await this.hass.callService("ha_govee_led_ble","export_effect",{id:w.id},{entity_id:o},!0,!0);return u($.response,o)}finally{this._busyKey=null}}async _editEffect(w){this._feedback=null;try{let r=await this._readEffect(w,"edit",jw);this._offerDraft(r.name,r.content,r.id,`Editing "${r.name}".`)}catch(r){this._feedback={kind:"error",text:F(r)}}}async _duplicateEffect(w,r){this._feedback=null;try{let u=await this._readEffect(w,"duplicate",jw),o=Vw(u.name,this._knownEffectNames(r));this._offerDraft(o,u.content,null,`Loaded "${o}" as a new draft. Review it, then save.`)}catch(u){this._feedback={kind:"error",text:F(u)}}}async _exportEffect(w){this._feedback=null;try{let r=await this._readEffect(w,"export",ew),u=tw(r),o=new Blob([`${JSON.stringify(u,null,2)}
`],{type:"application/json"}),$=URL.createObjectURL(o),b=Nr(pr(r.name),$);window.document.body.append(b),b.click(),b.remove(),URL.revokeObjectURL($),this._feedback={kind:"info",text:`Exported "${r.name}".`}}catch(r){this._feedback={kind:"error",text:F(r)}}}_chooseImportFile(){this.renderRoot.querySelector(".import-file")?.click()}async _loadImportFile(w){let r=w.target,u=r.files?.[0];if(r.value="",!u)return;try{this._importText=await u.text(),this._feedback={kind:"info",text:`Loaded ${u.name}. Review the JSON, then import it.`}}catch(o){this._feedback={kind:"error",text:F(o,"Could not read that file.")}}}_reviewImport(w){let r=this._segmentColors()?.length??R;try{let u=wr(this._importText,{model:this._targetModel(),segmentCount:r}),o=br(u.effect.name,this._knownEffectNames(w));this._offerDraft(o,u.effect.content,null,o===u.effect.name?`Imported "${o}" as a draft. Review it, then save.`:`Imported as "${o}" because that name already exists. Review it, then save.`,!0)}catch(u){this._feedback={kind:"error",text:F(u,"Could not import that effect.")}}}async _applyEffect(w){let r=this._config?.entity;if(!this.hass||!r)return;this._feedback=null;try{await this.hass.callService("light","turn_on",{effect:w.name},{entity_id:r})}catch(u){this._feedback={kind:"error",text:F(u)}}}_startRename(w){this._feedback=null,this._deletingId=null,this._renamingId=w.id,this._renameValue=w.name,this.updateComplete.then(()=>{let r=this.renderRoot.querySelector(".rename-input");r?.focus(),r?.select()})}_cancelRename(){this._renamingId=null,this._renameValue=""}async _commitRename(w){let r=this._config?.entity;if(!this.hass||!r)return;let u=this._renameValue.trim();try{if(await this.hass.callService("ha_govee_led_ble","rename_effect",{id:w.id,to:u},{entity_id:r}),this._editingId===w.id&&this._editingOriginalName!==null&&this._studioName.trim()===this._editingOriginalName){let o=this._currentContentSignature()===this._editingOriginalContent;if(this._studioName=u,this._editingOriginalName=u,o)this._draftBaseline=this._draftSignature()}this._renamingId=null,this._renameValue="",this._feedback={kind:"info",text:`Renamed to "${u}".`}}catch(o){this._feedback={kind:"error",text:F(o)}}}_askDelete(w){if(this._feedback=null,this._renamingId===w.id)this._cancelRename();this._deletingId=w.id,this.updateComplete.then(()=>{this.renderRoot.querySelector(".confirm-cancel")?.focus()})}_cancelDelete(){this._deletingId=null}_onDeleteKey(w){if(w.key==="Escape")w.preventDefault(),this._cancelDelete()}async _deleteEffect(w){let r=this._config?.entity;if(!this.hass||!r)return;this._deletingId=null;try{if(await this.hass.callService("ha_govee_led_ble","delete_effect",{id:w.id},{entity_id:r}),this._editingId===w.id)this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._draftBaseline="",this._feedback={kind:"info",text:`Deleted "${w.name}". Its Studio draft was kept as a new effect.`};else this._feedback={kind:"info",text:`Deleted "${w.name}".`};if(this._pendingDraft?.editingId===w.id)this._pendingDraft={...this._pendingDraft,editingId:null,feedback:`Loaded "${w.name}" as a new draft because the saved effect was deleted.`}}catch(u){this._feedback={kind:"error",text:F(u)}}}_onSaveKey(w,r){if(w.key==="Enter")w.preventDefault(),r()}_onRenameKey(w,r){if(w.key==="Enter")w.preventDefault(),this._commitRename(r);else if(w.key==="Escape")w.preventDefault(),this._cancelRename()}_drawNowPreview(){let w=this.renderRoot?.querySelector("canvas.preview");if(w)this._draw(w)}_draw(w){let r=window.devicePixelRatio||1,u=w.clientWidth||480,o=w.clientHeight||44;if(w.width!==Math.round(u*r))w.width=Math.round(u*r),w.height=Math.round(o*r);let $=w.getContext("2d");if(!$)return;$.setTransform(r,0,0,r,0,0),$.clearRect(0,0,u,o);let b=this._stops.map(j),p=R,n=3,E=(u-n*(p-1))/p;for(let q=0;q<p;q++){let B=rw(b,q/(p-1));$.fillStyle=`rgb(${B.map((Q)=>Math.round(Q)).join(",")})`;let z=q*(E+n);$.beginPath(),$.roundRect(z,0,E,o,4),$.fill()}}render(){if(!this._config)return J;let w=this._config.entity;if(!w)return this._notice("Select a light entity in the card configuration.");let r=this.hass?.states?.[w];if(!r||r.state==="unavailable"||r.state==="unknown")return this._notice(`${w} is unavailable.`);let u=this._segmentColors();if(!u)return this._notice(`${w} exposes no segment colours; this model has no addressable segments.`);return m`
      <ha-card>
        ${this._renderHeader(r)}
        <div class="body">
          ${this._tab==="now"?this._renderNow(u):J}
          ${this._tab==="studio"?this._renderStudio():J}
          ${this._tab==="library"?this._renderLibrary(r):J}
        </div>
      </ha-card>
    `}_notice(w){return m`
      <ha-card header=${Zr}>
        <div class="notice">${w}</div>
      </ha-card>
    `}_renderHeader(w){let r=typeof w.attributes?.effect==="string"&&w.attributes.effect!==""?w.attributes.effect:w.state==="on"?"Colour":"Off";return m`
      <div class="card-head">
        <div class="title">${Zr}</div>
        <div class="status">
          <span>Current:</span>
          <span class="current">${r}</span>
        </div>
        <div class="tabs" role="tablist" aria-label="Effect Studio sections">
          ${I.map((u)=>m`
              <button
                class="tab ${this._tab===u.id?"active":""}"
                id=${`tab-${u.id}`}
                role="tab"
                aria-selected=${this._tab===u.id?"true":"false"}
                aria-controls=${`panel-${u.id}`}
                tabindex=${this._tab===u.id?"0":"-1"}
                @click=${()=>this._selectTab(u.id)}
                @keydown=${this._onTabKey}
              >
                ${u.label}
              </button>
            `)}
        </div>
        ${this._feedback?m`<div class="feedback ${this._feedback.kind}" role="alert">
              ${this._feedback.text}
            </div>`:J}
        ${this._pendingDraft?m`
              <div class="draft-confirm" role="alertdialog" aria-label="Replace Studio draft">
                <span>Replace your unsaved Studio draft with "${this._pendingDraft.name}"?</span>
                <div class="row">
                  <button class="btn keep-draft" @click=${this._keepDraft}>Keep draft</button>
                  <button class="btn primary" @click=${this._confirmDraftReplacement}>
                    Replace draft
                  </button>
                </div>
              </div>
            `:J}
      </div>
    `}_renderScopeBand(w){return m`
      <div class="scope-band ${w}" role="note">
        <span class="dot" aria-hidden="true"></span>
        <span>${w==="live"?"Applies to the strip — changes show instantly":"Draft — builds a saved effect and never changes the strip"}</span>
      </div>
    `}_renderNow(w){let r=Array.from({length:R},(u,o)=>{let $=w[o];return $?Y($):null});return m`
      <div id="panel-now" role="tabpanel" aria-labelledby="tab-now">
        ${this._renderScopeBand("live")}
        <section>
          <div class="row heading">
            <span class="label">Segment painter</span>
            <span class="hint">${this._selection.size} selected</span>
          </div>
          ${this._renderStrip(r,"off")}
          <div class="row controls">
            <input
              type="color"
              aria-label="Paint colour"
              .value=${this._paintColor}
              @input=${(u)=>this._paintColor=u.target.value}
            />
            <button class="btn primary" @click=${this._applyPaint}>
              Apply to selection
            </button>
            <button class="btn" @click=${this._selectAll}>Select all</button>
            <button class="btn" @click=${this._clear}>Clear</button>
          </div>
        </section>
        ${this._renderGradient()}
        ${this._renderPresets()}
        ${this._renderSaveCurrent()}
      </div>
    `}_renderStrip(w,r,u=null){let o=(b)=>`segment-cell-${this._tab}-${this._studioKind}-${b}`,$=[];for(let b=1;b<=R;b++){let p=w[b-1]??null,n=this._selection.has(b),E=b===this._cursor,q=p?"painted":r==="off"?"off":r==="background"?"background":"unchanged",B=p?`background:${p}`:r==="background"&&u!==null?`--cell-background:${u}`:"";$.push(m`
        <div
          id=${o(b)}
          class="cell ${n?"sel":""} ${E?"cursor":""} ${p?"":r}"
          style=${B}
          role="option"
          aria-selected=${n?"true":"false"}
          aria-label=${`Segment ${b}, ${q}`}
          title=${`Segment ${b}`}
        >
          <span class="cell-num">${b}</span>
        </div>
      `)}return m`
      <div class="strip-scroll">
        <div
          class="strip"
          style="grid-template-columns: repeat(${R}, 1fr)"
          tabindex="0"
          role="listbox"
          aria-multiselectable="true"
          aria-activedescendant=${o(this._cursor)}
          aria-label=${`Segment painter, ${R} segments`}
          @pointerdown=${this._onDown}
          @keydown=${this._onKey}
        >
          ${$}
        </div>
      </div>
    `}_renderGradient(){return m`
      <section>
        ${this._renderStopEditor()}
        <div class="row heading">
          <span class="label">Gradient preview</span>
        </div>
        <canvas class="preview" height="44"></canvas>
        <div class="row controls">
          <button class="btn primary" @click=${this._applyGradient}>
            Apply gradient
          </button>
        </div>
      </section>
    `}_renderStopEditor(){let w=this._activeStops(),r=w.length,u=`linear-gradient(90deg, ${w.map((o,$)=>`${o} ${$/(r-1)*100}%`).join(", ")})`;return m`
      <div class="row heading">
        <span class="label">Gradient stops</span>
        <span class="hint">${r} of ${kw} to ${Cw}</span>
      </div>
      <div class="gradient-track">
        <div class="gradient-bar" style="background:${u}">
          ${w.map((o,$)=>m`
              <div
                class="handle ${this._dragStop===$?"dragging":""}"
                style="left:${this._dragStop===$&&this._dragFrac!==null?this._dragFrac*100:$/(r-1)*100}%;background:${o}"
                @pointerdown=${(b)=>this._startStopDrag(b,$)}
                title=${`Stop ${$+1}`}
              ></div>
            `)}
        </div>
      </div>
      <div class="stops">
        ${w.map((o,$)=>m`
            <div class="stop">
              <input
                type="color"
                aria-label=${`Stop ${$+1} colour`}
                .value=${o}
                @input=${(b)=>this._recolourStop($,b.target.value)}
              />
              <button
                class="btn tiny"
                ?disabled=${$===0}
                @click=${()=>this._moveStop($,-1)}
                aria-label=${`Move stop ${$+1} left`}
              >
                ←
              </button>
              <button
                class="btn tiny"
                ?disabled=${$===r-1}
                @click=${()=>this._moveStop($,1)}
                aria-label=${`Move stop ${$+1} right`}
              >
                →
              </button>
              <button
                class="btn tiny"
                ?disabled=${r<=kw}
                @click=${()=>this._removeStop($)}
                aria-label=${`Remove stop ${$+1}`}
                title="Remove stop"
              >
                &times;
              </button>
            </div>
          `)}
        <button
          class="btn tiny add"
          ?disabled=${r>=Cw}
          @click=${this._addStop}
          aria-label="Add stop"
          title="Add stop"
        >
          +
        </button>
      </div>
    `}_renderPresets(){return m`
      <section>
        <div class="row heading">
          <span class="label">Presets</span>
        </div>
        <div class="row presets">
          ${mr.map((w)=>m`
              <button
                class="preset"
                @click=${()=>this._applyPreset(w)}
                title=${w.name}
                aria-label=${w.name}
              >
                <span
                  class="swatch"
                  style="background:${this._presetSwatch(w.stops)}"
                ></span>
                <span class="preset-name">${w.name}</span>
              </button>
            `)}
        </div>
      </section>
    `}_renderSaveCurrent(){return m`
      <section>
        <div class="row heading">
          <span class="label">Save current</span>
        </div>
        <div class="row controls">
          <input
            class="effect-name"
            type="text"
            aria-label="New effect name"
            placeholder="Name this look"
            .value=${this._effectName}
            @input=${(w)=>this._effectName=w.target.value}
            @keydown=${(w)=>this._onSaveKey(w,()=>void this._saveCurrent())}
          />
          <button
            class="btn primary"
            ?disabled=${this._effectName.trim()===""}
            @click=${this._saveCurrent}
          >
            Save current as effect
          </button>
        </div>
        <p class="help">Snapshots the strip's current colours as a named effect.</p>
      </section>
    `}_renderStudio(){let w=this._availableKindDescriptors();return m`
      <div id="panel-studio" role="tabpanel" aria-labelledby="tab-studio">
        ${this._renderScopeBand("draft")}
        <section>
          <div class="row heading">
            <span class="label">Effect kind</span>
          </div>
          <div class="kinds" role="radiogroup" aria-label="Effect kind" @keydown=${this._onKindKey}>
            ${w.map((r)=>m`
                <button
                  class="kind ${this._studioKind===r.id?"active":""}"
                  role="radio"
                  aria-checked=${this._studioKind===r.id?"true":"false"}
                  tabindex=${this._studioKind===r.id?"0":"-1"}
                  ?disabled=${this._editingId!==null&&this._studioKind!==r.id}
                  @click=${()=>this._selectKind(r.id)}
                >
                  ${r.label}
                </button>
              `)}
          </div>
          ${Qr.length>0?m`
                <div class="kinds-soon">
                  <span>Coming next:</span>
                  ${Qr.map((r)=>m`
                      <button class="kind soon" disabled aria-disabled="true">
                        ${r.label}<span class="soon-tag">soon</span>
                      </button>
                    `)}
                </div>
              `:J}
        </section>
        ${this._studioKind==="static"?this._renderStaticEditor():this._studioKind==="gradient"?this._renderGradientAuthor():this._studioKind==="sketch"?this._renderSketchAuthor():this._studioKind==="flat"?this._renderFlatAuthor():this._studioKind==="combo"?this._renderComboAuthor():this._renderPendingAuthor()}
      </div>
    `}_renderStaticEditor(){let w=this._staticColors.filter((u)=>u!==null).length,r=zr(this._staticColors.map((u)=>u===null?null:j(u)),this._staticBrightness);return m`
      <section>
        <div class="row heading">
          <span class="label">Static segments</span>
          <span class="hint">${w} painted · ${this._selection.size} selected</span>
        </div>
        ${this._renderStrip(this._staticColors,"unchanged")}
        <div class="row controls">
          <input
            type="color"
            aria-label="Paint colour"
            .value=${this._paintColor}
            @input=${(u)=>this._paintColor=u.target.value}
          />
          <button class="btn primary" @click=${this._paintStatic}>Paint selected</button>
          <button class="btn" @click=${this._setUnchangedStatic}>Clear selected</button>
          <button class="btn" @click=${this._selectAll}>Select all</button>
          <button class="btn" @click=${this._resetStatic}>Reset</button>
        </div>
        <p class="help">
          Paint a colour onto chosen segments; hatched segments are left as they are on the strip.
        </p>
        ${this._renderStudioSave(r,"Paint at least one segment to save.")}
      </section>
    `}_renderSketchAuthor(){let w=this._sketchColors.filter((o)=>o!==null).length,r=Qw(this._sketchColors.map((o)=>o===null?null:j(o)),this._sketchMotion,this._sketchSpeed,this._sketchBrightness,j(this._sketchBackground)),u=or(r).map(Y);return m`
      <section>
        <div class="row heading">
          <span class="label">Sketch foreground</span>
          <span class="hint">${w} painted · ${this._selection.size} selected</span>
        </div>
        ${this._renderStrip(this._sketchColors,"background",this._sketchBackground)}
        <div class="row controls">
          <label class="colour-control">
            <span>Foreground</span>
            <input
              type="color"
              aria-label="Sketch foreground colour"
              .value=${this._paintColor}
              @input=${(o)=>this._paintColor=o.target.value}
            />
          </label>
          <label class="colour-control">
            <span>Background</span>
            <input
              type="color"
              aria-label="Sketch background colour"
              .value=${this._sketchBackground}
              @input=${(o)=>this._sketchBackground=o.target.value}
            />
          </label>
          <button class="btn primary" @click=${this._paintSketch}>Paint selected</button>
          <button class="btn" @click=${this._clearSketchSelection}>Use background</button>
          <button class="btn" @click=${this._selectAll}>Select all</button>
          <button class="btn" @click=${this._resetSketch}>Reset</button>
        </div>
        <p class="help">
          Hatched cells use the background; solid cells are the animated foreground palette.
        </p>
      </section>
      <section>
        <div class="row heading">
          <span class="label">Motion</span>
        </div>
        <div
          class="motion-grid"
          role="radiogroup"
          aria-label="Sketch motion"
          @keydown=${this._onMotionKey}
        >
          ${ww.map((o)=>m`
              <button
                class="motion ${this._sketchMotion===o.code?"active":""}"
                role="radio"
                aria-checked=${this._sketchMotion===o.code?"true":"false"}
                tabindex=${this._sketchMotion===o.code?"0":"-1"}
                @click=${()=>this._sketchMotion=o.code}
              >
                ${o.label}
              </button>
            `)}
        </div>
        <label class="range-row">
          <span>Speed</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._sketchSpeed)}
            aria-label=${`Sketch speed, ${this._sketchSpeed} percent`}
            @input=${(o)=>this._sketchSpeed=Number(o.target.value)}
          />
          <output>${this._sketchSpeed}%</output>
        </label>
        <label class="range-row">
          <span>Brightness</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._sketchBrightness)}
            aria-label=${`Sketch brightness, ${this._sketchBrightness} percent`}
            @input=${(o)=>this._sketchBrightness=Number(o.target.value)}
          />
          <output>${this._sketchBrightness}%</output>
        </label>
      </section>
      <section>
        <div class="row heading">
          <span class="label">Representative preview</span>
          <span class="preview-badge">Approximate · animated on device</span>
        </div>
        ${this._renderPreviewStrip(u)}
        ${this._renderStudioSave(!0,"")}
      </section>
    `}_renderPaletteEditor(w,r,u,o,$,b,p){return m`
      <div class="row heading">
        <span class="label">${u}</span>
        <span class="hint">${w.length} of ${r}</span>
      </div>
      <div class="palette-editor">
        ${w.map((n,E)=>m`
            <div class="palette-chip">
              <span class="palette-number">${E+1}</span>
              <input
                type="color"
                aria-label=${`${u} colour ${E+1}`}
                .value=${n}
                @input=${(q)=>o(E,q.target.value)}
              />
              <button
                class="btn tiny"
                ?disabled=${E===0}
                @click=${()=>p(E,-1)}
                aria-label=${`Move colour ${E+1} left`}
              >
                ←
              </button>
              <button
                class="btn tiny"
                ?disabled=${E===w.length-1}
                @click=${()=>p(E,1)}
                aria-label=${`Move colour ${E+1} right`}
              >
                →
              </button>
              <button
                class="btn tiny danger"
                @click=${()=>b(E)}
                aria-label=${`Remove colour ${E+1}`}
              >
                ×
              </button>
            </div>
          `)}
        <button
          class="btn palette-add"
          ?disabled=${w.length>=r}
          @click=${$}
        >
          Add colour
        </button>
      </div>
    `}_renderFlatAuthor(){let w=V(this._flatFamily),r=this._flatPalette.length===0?[]:Array.from({length:R},(u,o)=>this._flatPalette[o%this._flatPalette.length]);return m`
      <section>
        <div class="row heading">
          <span class="label">Animation family</span>
          <span class="hint">Human-labelled catalogue</span>
        </div>
        <div
          class="family-grid"
          role="radiogroup"
          aria-label="Flat animation family"
          @keydown=${this._onFlatFamilyKey}
        >
          ${Z.map((u)=>m`
              <button
                class="family ${u.family===this._flatFamily?"active":""}"
                role="radio"
                aria-checked=${u.family===this._flatFamily?"true":"false"}
                tabindex=${u.family===this._flatFamily?"0":"-1"}
                @click=${()=>this._selectFlatFamily(u.family)}
              >
                ${u.label}
              </button>
            `)}
        </div>
        <div class="row heading">
          <span class="label">Variant</span>
          <span class="hint">Up to ${w.palette_max} colours</span>
        </div>
        <div
          class="variant-grid"
          role="radiogroup"
          aria-label=${`${w.label} variant`}
          @keydown=${this._onFlatVariantKey}
        >
          ${w.variants.map((u)=>m`
              <button
                class="variant ${u.variant===this._flatVariant?"active":""}"
                role="radio"
                aria-checked=${u.variant===this._flatVariant?"true":"false"}
                tabindex=${u.variant===this._flatVariant?"0":"-1"}
                @click=${()=>this._flatVariant=u.variant}
              >
                ${u.label}
              </button>
            `)}
        </div>
        <p class="help">${w.description}</p>
      </section>
      <section>
        ${this._renderPaletteEditor(this._flatPalette,w.palette_max,"Shared palette order",(u,o)=>this._setFlatPaletteColour(u,o),()=>this._addFlatPaletteColour(),(u)=>this._removeFlatPaletteColour(u),(u,o)=>this._moveFlatPaletteColour(u,o))}
        ${r.length>0?m`
              <div class="row heading">
                <span class="label">Representative preview</span>
                <span class="preview-badge">Approximate · animated on device</span>
              </div>
              ${this._renderPreviewStrip(r)}
            `:m`<p class="help">Add at least one colour to preview and save this effect.</p>`}
      </section>
      <section>
        <label class="range-row">
          <span>${w.control_label}</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._flatSpeed)}
            aria-label=${`${w.control_label}, ${this._flatSpeed} percent`}
            @input=${(u)=>this._flatSpeed=Number(u.target.value)}
          />
          <output>${this._flatSpeed}%</output>
        </label>
        <button class="btn" @click=${this._resetFlat}>Reset Flat draft</button>
        ${this._renderStudioSave(this._flatPalette.length>0,"Add at least one palette colour to save.")}
      </section>
    `}_renderComboAuthor(){let w=this._comboPalette.length===0?[]:Array.from({length:R},(r,u)=>this._comboPalette[u%this._comboPalette.length]);return m`
      <section>
        <div class="row heading">
          <span class="label">Effect chain</span>
          <span class="hint">${this._comboEffects.length} of 4 steps</span>
        </div>
        ${this._comboEffects.length===0?m`<p class="help">Add at least one Flat effect to the chain.</p>`:m`
              <ol class="combo-chain">
                ${this._comboEffects.map((r,u)=>{let o=V(r.family);return m`
                    <li class="combo-step">
                      <span class="combo-number">${u+1}</span>
                      <label>
                        <span class="sr-only">Step ${u+1} family</span>
                        <select
                          aria-label=${`Step ${u+1} family`}
                          .value=${String(r.family)}
                          @change=${($)=>this._setComboFamily(u,Number($.target.value))}
                        >
                          ${Z.map(($)=>m`
                              <option value=${String($.family)}>${$.label}</option>
                            `)}
                        </select>
                      </label>
                      <label>
                        <span class="sr-only">Step ${u+1} variant</span>
                        <select
                          aria-label=${`Step ${u+1} variant`}
                          .value=${String(r.variant)}
                          @change=${($)=>this._setComboVariant(u,Number($.target.value))}
                        >
                          ${o.variants.map(($)=>m`
                              <option value=${String($.variant)}>${$.label}</option>
                            `)}
                        </select>
                      </label>
                      <div class="combo-actions">
                        <button
                          class="btn tiny"
                          ?disabled=${u===0}
                          @click=${()=>this._moveComboStep(u,-1)}
                          aria-label=${`Move step ${u+1} up`}
                        >
                          ↑
                        </button>
                        <button
                          class="btn tiny"
                          ?disabled=${u===this._comboEffects.length-1}
                          @click=${()=>this._moveComboStep(u,1)}
                          aria-label=${`Move step ${u+1} down`}
                        >
                          ↓
                        </button>
                        <button
                          class="btn tiny danger"
                          @click=${()=>this._removeComboStep(u)}
                          aria-label=${`Remove step ${u+1}`}
                        >
                          ×
                        </button>
                      </div>
                    </li>
                  `})}
              </ol>
            `}
        <button
          class="btn"
          ?disabled=${this._comboEffects.length>=4}
          @click=${this._addComboStep}
        >
          Add step
        </button>
      </section>
      <section>
        ${this._renderPaletteEditor(this._comboPalette,8,"Shared palette order",(r,u)=>this._setComboPaletteColour(r,u),()=>this._addComboPaletteColour(),(r)=>this._removeComboPaletteColour(r),(r,u)=>this._moveComboPaletteColour(r,u))}
        ${w.length>0?m`
              <div class="row heading">
                <span class="label">Sequence preview</span>
                <span class="preview-badge">Approximate · animated on device</span>
              </div>
              ${this._renderPreviewStrip(w)}
            `:m`<p class="help">Add at least one shared palette colour.</p>`}
      </section>
      <section>
        <label class="range-row">
          <span>Speed</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._comboSpeed)}
            aria-label=${`Combo speed, ${this._comboSpeed} percent`}
            @input=${(r)=>this._comboSpeed=Number(r.target.value)}
          />
          <output>${this._comboSpeed}%</output>
        </label>
        <button class="btn" @click=${this._resetCombo}>Reset Combo draft</button>
        ${this._renderStudioSave(this._comboEffects.length>0&&this._comboPalette.length>0,this._comboEffects.length===0?"Add at least one effect step to save.":"Add at least one shared palette colour to save.")}
      </section>
    `}_renderPendingAuthor(){let w=y.find((u)=>u.id===this._studioKind)?.label??this._studioKind,r=this._loadedContent?.kind===this._studioKind;return m`
      <section class="pending-author">
        <div class="row heading">
          <span class="label">${w}</span>
          <span class="hint">Editor coming next</span>
        </div>
        <p class="help">
          ${r?`This ${w} effect is loaded safely, but this editor is not available in the current build.`:`The ${w} editor will be enabled in the next Studio phase.`}
        </p>
        ${this._editingId!==null?m`<button class="btn" @click=${this._cancelEdit}>Cancel edit</button>`:J}
      </section>
    `}_renderGradientAuthor(){let w=uw(this._studioStops.map(j),R).map(Y);return m`
      <section>
        ${this._renderStopEditor()}
        <div class="row heading">
          <span class="label">Draft preview · ${R} segments</span>
        </div>
        ${this._renderPreviewStrip(w)}
        <p class="help">Saves the colour stops as a gradient effect.</p>
        ${this._renderStudioSave(!0,"")}
      </section>
    `}_renderPreviewStrip(w){return m`
      <div class="strip-scroll">
        <div
          class="strip preview-strip"
          style="grid-template-columns: repeat(${R}, 1fr)"
          aria-hidden="true"
        >
          ${w.map((r,u)=>m`
              <div class="cell" style="background:${r}" title=${`Segment ${u+1}`}>
                <span class="cell-num">${u+1}</span>
              </div>
            `)}
        </div>
      </div>
    `}_renderStudioSave(w,r){let u=this._studioName.trim()!=="",o=this._editingId!==null;return m`
      ${o?m`<div class="edit-band" role="status">
            <span>Editing a saved effect. Update keeps its stable ID and effect kind.</span>
            <button class="btn" @click=${this._cancelEdit}>Cancel edit</button>
          </div>`:J}
      <div class="row controls">
        <input
          class="effect-name"
          type="text"
          aria-label="Effect name"
          placeholder="Name this effect"
          .value=${this._studioName}
          @input=${($)=>this._studioName=$.target.value}
          @keydown=${($)=>this._onSaveKey($,()=>void this._saveStudio())}
        />
        <button
          class="btn primary"
          ?disabled=${!u||!w}
          @click=${this._saveStudio}
        >
          ${o?"Update effect":"Save effect"}
        </button>
      </div>
      ${!w&&r!==""?m`<p class="help">${r}</p>`:J}
    `}_renderLibrary(w){let r=ow(w.attributes?.custom_effects),u=ow(w.attributes?.quarantined_custom_effects),o=[...r,...u],$=typeof w.attributes?.effect==="string"?w.attributes.effect:null;return m`
      <div id="panel-library" role="tabpanel" aria-labelledby="tab-library">
        <section>
          <div class="row heading">
            <span class="label">Saved effects</span>
            <span class="hint">${r.length} available</span>
          </div>
          ${r.length===0?m`<p class="help">
                No custom effects saved yet. Create one in the Studio tab, or snapshot the strip from
                the Now tab.
              </p>`:m`
                <p class="help">Select an effect to apply it.</p>
                <ul class="effects" role="list">
                  ${r.map((b)=>this._renderEffectRow(b,$,o))}
                </ul>
              `}
        </section>
        ${u.length===0?J:m`
              <section>
                <div class="row heading">
                  <span class="label">Unavailable on this model</span>
                  <span class="hint">${u.length} preserved</span>
                </div>
                <p class="help">
                  These effects are kept for export or deletion, but cannot be applied or edited on
                  this light.
                </p>
                <ul class="effects" role="list">
                  ${u.map((b)=>this._renderQuarantinedEffectRow(b))}
                </ul>
              </section>
            `}
        <section>
          <details class="import-panel">
            <summary>Import effect JSON</summary>
            <div class="import-body">
              <textarea
                class="import-json"
                aria-label="Effect JSON"
                placeholder="Paste an exported Govee effect here"
                .value=${this._importText}
                @input=${(b)=>this._importText=b.target.value}
              ></textarea>
              <input
                class="import-file"
                type="file"
                accept=".json,application/json"
                @change=${this._loadImportFile}
              />
              <div class="row controls">
                <button class="btn" @click=${this._chooseImportFile}>Load JSON file</button>
                <button
                  class="btn primary"
                  ?disabled=${this._importText.trim()===""}
                  @click=${()=>this._reviewImport(o)}
                >
                  Review import
                </button>
                <button
                  class="btn"
                  ?disabled=${this._importText===""}
                  @click=${()=>this._importText=""}
                >
                  Clear
                </button>
              </div>
              <p class="help">
                Import opens an untrusted file as a Studio draft. Nothing is saved until you review it.
              </p>
            </div>
          </details>
        </section>
      </div>
    `}_renderEffectRow(w,r,u){if(this._renamingId===w.id)return m`
        <li class="effect renaming">
          <input
            class="effect-name rename-input"
            type="text"
            aria-label=${`New name for ${w.name}`}
            .value=${this._renameValue}
            @input=${(b)=>this._renameValue=b.target.value}
            @keydown=${(b)=>this._onRenameKey(b,w)}
          />
          <button class="btn primary" @click=${()=>this._commitRename(w)}>
            Save
          </button>
          <button class="btn" @click=${this._cancelRename}>Cancel</button>
        </li>
      `;if(this._deletingId===w.id)return m`
        <li class="effect">
          <span class="confirm-text">Delete "${w.name}"?</span>
          <button
            class="btn confirm-cancel"
            @click=${this._cancelDelete}
            @keydown=${this._onDeleteKey}
          >
            Cancel
          </button>
          <button
            class="btn danger primary"
            @click=${()=>this._deleteEffect(w)}
            @keydown=${this._onDeleteKey}
          >
            Delete
          </button>
        </li>
      `;let o=r!==null&&r===w.name,$=this._busyKey?.endsWith(`:${w.id}`)??!1;return m`
      <li class="effect ${o?"active":""}">
        <div class="effect-main">
          ${o?m`<span class="badge-active" aria-current="true">✓ Active</span>`:m`<button
                class="btn primary"
                @click=${()=>this._applyEffect(w)}
                aria-label=${`Apply ${w.name}`}
              >
                Apply
              </button>`}
          <span class="effect-label" title=${w.name}>${w.name}</span>
        </div>
        <div class="effect-actions">
          <button
            class="btn"
            ?disabled=${$}
            @click=${()=>void this._editEffect(w)}
            aria-label=${`Edit ${w.name}`}
          >
            Edit
          </button>
          <button
            class="btn"
            ?disabled=${$}
            @click=${()=>void this._duplicateEffect(w,u)}
            aria-label=${`Duplicate ${w.name}`}
          >
            Duplicate
          </button>
          <details class="effect-more">
            <summary class="btn">More</summary>
            <div class="more-actions">
              <button
                class="btn"
                ?disabled=${$}
                @click=${()=>void this._exportEffect(w)}
                aria-label=${`Export ${w.name}`}
              >
                ${$?"Working…":"Export"}
              </button>
              <button
                class="btn"
                @click=${()=>this._startRename(w)}
                aria-label=${`Rename ${w.name}`}
              >
                Rename
              </button>
              <button
                class="btn danger"
                @click=${()=>this._askDelete(w)}
                aria-label=${`Delete ${w.name}`}
              >
                Delete
              </button>
            </div>
          </details>
        </div>
      </li>
    `}_renderQuarantinedEffectRow(w){if(this._deletingId===w.id)return m`
        <li class="effect quarantined">
          <span class="confirm-text">Delete "${w.name}"?</span>
          <button class="btn confirm-cancel" @click=${this._cancelDelete}>Cancel</button>
          <button class="btn danger primary" @click=${()=>this._deleteEffect(w)}>
            Delete
          </button>
        </li>
      `;let r=this._busyKey?.endsWith(`:${w.id}`)??!1;return m`
      <li class="effect quarantined">
        <div class="effect-main">
          <span class="badge-unavailable">Unavailable</span>
          <span class="effect-label" title=${w.name}>${w.name}</span>
        </div>
        <div class="effect-actions">
          <button
            class="btn"
            ?disabled=${r}
            @click=${()=>void this._exportEffect(w)}
            aria-label=${`Export ${w.name}`}
          >
            ${r?"Working…":"Export"}
          </button>
          <button
            class="btn danger"
            @click=${()=>this._askDelete(w)}
            aria-label=${`Delete ${w.name}`}
          >
            Delete
          </button>
        </div>
      </li>
    `}static styles=dw}customElements.define("govee-led-ble-card",Vr);window.customCards=window.customCards||[];window.customCards.push({type:"govee-led-ble-card",name:"Govee LED BLE",description:"Paint, compose and save custom effects for a segment-capable Govee LED BLE light.",preview:!1});console.info("%c govee-led-ble-card ","background:#1982c4;color:#fff;border-radius:3px","loaded");
