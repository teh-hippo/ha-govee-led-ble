var v=globalThis,o=v.ShadowRoot&&(v.ShadyCSS===void 0||v.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,c=Symbol(),q0=new WeakMap;class i{constructor(z,J,Z){if(this._$cssResult$=!0,Z!==c)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=z,this.t=J}get styleSheet(){let z=this.i,J=this.t;if(o&&z===void 0){let Z=J!==void 0&&J.length===1;Z&&(z=q0.get(J)),z===void 0&&((this.i=z=new CSSStyleSheet).replaceSync(this.cssText),Z&&q0.set(J,z))}return z}toString(){return this.cssText}}var l0=(z)=>new i(typeof z=="string"?z:z+"",void 0,c),g=(z,...J)=>{let Z=z.length===1?z[0]:J.reduce((Q,Y,F)=>Q+((q)=>{if(q._$cssResult$===!0)return q.cssText;if(typeof q=="number")return q;throw Error("Value passed to 'css' function must be a 'css' function result: "+q+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(Y)+z[F+1],z[0]);return new i(Z,z,c)},a0=(z,J)=>{if(o)z.adoptedStyleSheets=J.map((Z)=>Z instanceof CSSStyleSheet?Z:Z.styleSheet);else for(let Z of J){let Q=document.createElement("style"),Y=v.litNonce;Y!==void 0&&Q.setAttribute("nonce",Y),Q.textContent=Z.cssText,z.appendChild(Q)}},j0=o?(z)=>z:(z)=>z instanceof CSSStyleSheet?((J)=>{let Z="";for(let Q of J.cssRules)Z+=Q.cssText;return l0(Z)})(z):z,{is:n0,defineProperty:o0,getOwnPropertyDescriptor:c0,getOwnPropertyNames:i0,getOwnPropertySymbols:r0,getPrototypeOf:s0}=Object,m=globalThis,V0=m.trustedTypes,e0=V0?V0.emptyScript:"",t0=m.reactiveElementPolyfillSupport,d=(z,J)=>z,n={toAttribute(z,J){switch(J){case Boolean:z=z?e0:null;break;case Object:case Array:z=z==null?z:JSON.stringify(z)}return z},fromAttribute(z,J){let Z=z;switch(J){case Boolean:Z=z!==null;break;case Number:Z=z===null?null:Number(z);break;case Object:case Array:try{Z=JSON.parse(z)}catch(Q){Z=null}}return Z}},R0=(z,J)=>!n0(z,J),W0={attribute:!0,type:String,converter:n,reflect:!1,useDefault:!1,hasChanged:R0};Symbol.metadata??=Symbol("metadata"),m.litPropertyMetadata??=new WeakMap;class I extends HTMLElement{static addInitializer(z){this.o(),(this.l??=[]).push(z)}static get observedAttributes(){return this.finalize(),this.u&&[...this.u.keys()]}static createProperty(z,J=W0){if(J.state&&(J.attribute=!1),this.o(),this.prototype.hasOwnProperty(z)&&((J=Object.create(J)).wrapped=!0),this.elementProperties.set(z,J),!J.noAccessor){let Z=Symbol(),Q=this.getPropertyDescriptor(z,Z,J);Q!==void 0&&o0(this.prototype,z,Q)}}static getPropertyDescriptor(z,J,Z){let{get:Q,set:Y}=c0(this.prototype,z)??{get(){return this[J]},set(F){this[J]=F}};return{get:Q,set(F){let q=Q?.call(this);Y?.call(this,F),this.requestUpdate(z,q,Z)},configurable:!0,enumerable:!0}}static getPropertyOptions(z){return this.elementProperties.get(z)??W0}static o(){if(this.hasOwnProperty(d("elementProperties")))return;let z=s0(this);z.finalize(),z.l!==void 0&&(this.l=[...z.l]),this.elementProperties=new Map(z.elementProperties)}static finalize(){if(this.hasOwnProperty(d("finalized")))return;if(this.finalized=!0,this.o(),this.hasOwnProperty(d("properties"))){let J=this.properties,Z=[...i0(J),...r0(J)];for(let Q of Z)this.createProperty(Q,J[Q])}let z=this[Symbol.metadata];if(z!==null){let J=litPropertyMetadata.get(z);if(J!==void 0)for(let[Z,Q]of J)this.elementProperties.set(Z,Q)}this.u=new Map;for(let[J,Z]of this.elementProperties){let Q=this.p(J,Z);Q!==void 0&&this.u.set(Q,J)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(z){let J=[];if(Array.isArray(z)){let Z=new Set(z.flat(1/0).reverse());for(let Q of Z)J.unshift(j0(Q))}else z!==void 0&&J.push(j0(z));return J}static p(z,J){let Z=J.attribute;return Z===!1?void 0:typeof Z=="string"?Z:typeof z=="string"?z.toLowerCase():void 0}constructor(){super(),this.v=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this.m=null,this._()}_(){this.S=new Promise((z)=>this.enableUpdating=z),this._$AL=new Map,this.$(),this.requestUpdate(),this.constructor.l?.forEach((z)=>z(this))}addController(z){(this.P??=new Set).add(z),this.renderRoot!==void 0&&this.isConnected&&z.hostConnected?.()}removeController(z){this.P?.delete(z)}$(){let z=new Map,J=this.constructor.elementProperties;for(let Z of J.keys())this.hasOwnProperty(Z)&&(z.set(Z,this[Z]),delete this[Z]);z.size>0&&(this.v=z)}createRenderRoot(){let z=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return a0(z,this.constructor.elementStyles),z}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this.P?.forEach((z)=>z.hostConnected?.())}enableUpdating(z){}disconnectedCallback(){this.P?.forEach((z)=>z.hostDisconnected?.())}attributeChangedCallback(z,J,Z){this._$AK(z,Z)}C(z,J){let Z=this.constructor.elementProperties.get(z),Q=this.constructor.p(z,Z);if(Q!==void 0&&Z.reflect===!0){let Y=(Z.converter?.toAttribute!==void 0?Z.converter:n).toAttribute(J,Z.type);this.m=z,Y==null?this.removeAttribute(Q):this.setAttribute(Q,Y),this.m=null}}_$AK(z,J){let Z=this.constructor,Q=Z.u.get(z);if(Q!==void 0&&this.m!==Q){let Y=Z.getPropertyOptions(Q),F=typeof Y.converter=="function"?{fromAttribute:Y.converter}:Y.converter?.fromAttribute!==void 0?Y.converter:n;this.m=Q;let q=F.fromAttribute(J,Y.type);this[Q]=q??this.T?.get(Q)??q,this.m=null}}requestUpdate(z,J,Z,Q=!1,Y){if(z!==void 0){let F=this.constructor;if(Q===!1&&(Y=this[z]),Z??=F.getPropertyOptions(z),!((Z.hasChanged??R0)(Y,J)||Z.useDefault&&Z.reflect&&Y===this.T?.get(z)&&!this.hasAttribute(F.p(z,Z))))return;this.M(z,J,Z)}this.isUpdatePending===!1&&(this.S=this.k())}M(z,J,{useDefault:Z,reflect:Q,wrapped:Y},F){Z&&!(this.T??=new Map).has(z)&&(this.T.set(z,F??J??this[z]),Y!==!0||F!==void 0)||(this._$AL.has(z)||(this.hasUpdated||Z||(J=void 0),this._$AL.set(z,J)),Q===!0&&this.m!==z&&(this.A??=new Set).add(z))}async k(){this.isUpdatePending=!0;try{await this.S}catch(J){Promise.reject(J)}let z=this.scheduleUpdate();return z!=null&&await z,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this.v){for(let[Q,Y]of this.v)this[Q]=Y;this.v=void 0}let Z=this.constructor.elementProperties;if(Z.size>0)for(let[Q,Y]of Z){let{wrapped:F}=Y,q=this[Q];F!==!0||this._$AL.has(Q)||q===void 0||this.M(Q,void 0,Y,q)}}let z=!1,J=this._$AL;try{z=this.shouldUpdate(J),z?(this.willUpdate(J),this.P?.forEach((Z)=>Z.hostUpdate?.()),this.update(J)):this.U()}catch(Z){throw z=!1,this.U(),Z}z&&this._$AE(J)}willUpdate(z){}_$AE(z){this.P?.forEach((J)=>J.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(z)),this.updated(z)}U(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this.S}shouldUpdate(z){return!0}update(z){this.A&&=this.A.forEach((J)=>this.C(J,this[J])),this.U()}updated(z){}firstUpdated(z){}}I.elementStyles=[],I.shadowRootOptions={mode:"open"},I[d("elementProperties")]=new Map,I[d("finalized")]=new Map,t0?.({ReactiveElement:I}),(m.reactiveElementVersions??=[]).push("2.1.2");var r=globalThis,$0=(z)=>z,b=r.trustedTypes,B0=b?b.createPolicy("lit-html",{createHTML:(z)=>z}):void 0,D0="$lit$",G=`lit$${Math.random().toFixed(9).slice(2)}$`,G0="?"+G,z8=`<${G0}>`,M=document,k=()=>M.createComment(""),N=(z)=>z===null||typeof z!="object"&&typeof z!="function",s=Array.isArray,J8=(z)=>s(z)||typeof z?.[Symbol.iterator]=="function",a=`[ 	
\f\r]`,E=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,H0=/-->/g,L0=/>/g,K=RegExp(`>|${a}(?:([^\\s"'>=/]+)(${a}*=${a}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),P0=/'/g,X0=/"/g,C0=/^(?:script|style|textarea|title)$/i,e=(z)=>(J,...Z)=>({_$litType$:z,strings:J,values:Z}),V=e(1),$8=e(2),B8=e(3),_=Symbol.for("lit-noChange"),B=Symbol.for("lit-nothing"),w0=new WeakMap,U=M.createTreeWalker(M,129);function K0(z,J){if(!s(z)||!z.hasOwnProperty("raw"))throw Error("invalid template strings array");return B0!==void 0?B0.createHTML(J):J}var Z8=(z,J)=>{let Z=z.length-1,Q=[],Y,F=J===2?"<svg>":J===3?"<math>":"",q=E;for(let j=0;j<Z;j++){let $=z[j],C,W,H=-1,P=0;for(;P<$.length&&(q.lastIndex=P,W=q.exec($),W!==null);)P=q.lastIndex,q===E?W[1]==="!--"?q=H0:W[1]!==void 0?q=L0:W[2]!==void 0?(C0.test(W[2])&&(Y=RegExp("</"+W[2],"g")),q=K):W[3]!==void 0&&(q=K):q===K?W[0]===">"?(q=Y??E,H=-1):W[1]===void 0?H=-2:(H=q.lastIndex-W[2].length,C=W[1],q=W[3]===void 0?K:W[3]==='"'?X0:P0):q===X0||q===P0?q=K:q===H0||q===L0?q=E:(q=K,Y=void 0);let w=q===K&&z[j+1].startsWith("/>")?" ":"";F+=q===E?$+z8:H>=0?(Q.push(C),$.slice(0,H)+D0+$.slice(H)+G+w):$+G+(H===-2?j:w)}return[K0(z,F+(z[Z]||"<?>")+(J===2?"</svg>":J===3?"</math>":"")),Q]};class x{constructor({strings:z,_$litType$:J},Z){let Q;this.parts=[];let Y=0,F=0,q=z.length-1,j=this.parts,[$,C]=Z8(z,J);if(this.el=x.createElement($,Z),U.currentNode=this.el.content,J===2||J===3){let W=this.el.content.firstChild;W.replaceWith(...W.childNodes)}for(;(Q=U.nextNode())!==null&&j.length<q;){if(Q.nodeType===1){if(Q.hasAttributes())for(let W of Q.getAttributeNames())if(W.endsWith(D0)){let H=C[F++],P=Q.getAttribute(W).split(G),w=/([.?@])?(.*)/.exec(H);j.push({type:1,index:Y,name:w[2],strings:P,ctor:w[1]==="."?U0:w[1]==="?"?M0:w[1]==="@"?_0:T}),Q.removeAttribute(W)}else W.startsWith(G)&&(j.push({type:6,index:Y}),Q.removeAttribute(W));if(C0.test(Q.tagName)){let W=Q.textContent.split(G),H=W.length-1;if(H>0){Q.textContent=b?b.emptyScript:"";for(let P=0;P<H;P++)Q.append(W[P],k()),U.nextNode(),j.push({type:2,index:++Y});Q.append(W[H],k())}}}else if(Q.nodeType===8)if(Q.data===G0)j.push({type:2,index:Y});else{let W=-1;for(;(W=Q.data.indexOf(G,W+1))!==-1;)j.push({type:7,index:Y}),W+=G.length-1}Y++}}static createElement(z,J){let Z=M.createElement("template");return Z.innerHTML=z,Z}}function A(z,J,Z=z,Q){if(J===_)return J;let Y=Q!==void 0?Z.N?.[Q]:Z.O,F=N(J)?void 0:J._$litDirective$;return Y?.constructor!==F&&(Y?._$AO?.(!1),F===void 0?Y=void 0:(Y=new F(z),Y._$AT(z,Z,Q)),Q!==void 0?(Z.N??=[])[Q]=Y:Z.O=Y),Y!==void 0&&(J=A(z,Y._$AS(z,J.values),Y,Q)),J}class I0{constructor(z,J){this._$AV=[],this._$AN=void 0,this._$AD=z,this._$AM=J}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}R(z){let{el:{content:J},parts:Z}=this._$AD,Q=(z?.creationScope??M).importNode(J,!0);U.currentNode=Q;let Y=U.nextNode(),F=0,q=0,j=Z[0];for(;j!==void 0;){if(F===j.index){let $;j.type===2?$=new u(Y,Y.nextSibling,this,z):j.type===1?$=new j.ctor(Y,j.name,j.strings,this,z):j.type===6&&($=new A0(Y,this,z)),this._$AV.push($),j=Z[++q]}F!==j?.index&&(Y=U.nextNode(),F++)}return U.currentNode=M,Q}V(z){let J=0;for(let Z of this._$AV)Z!==void 0&&(Z.strings!==void 0?(Z._$AI(z,Z,J),J+=Z.strings.length-2):Z._$AI(z[J])),J++}}class u{get _$AU(){return this._$AM?._$AU??this.D}constructor(z,J,Z,Q){this.type=2,this._$AH=B,this._$AN=void 0,this._$AA=z,this._$AB=J,this._$AM=Z,this.options=Q,this.D=Q?.isConnected??!0}get parentNode(){let z=this._$AA.parentNode,J=this._$AM;return J!==void 0&&z?.nodeType===11&&(z=J.parentNode),z}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(z,J=this){z=A(this,z,J),N(z)?z===B||z==null||z===""?(this._$AH!==B&&this._$AR(),this._$AH=B):z!==this._$AH&&z!==_&&this.L(z):z._$litType$!==void 0?this.j(z):z.nodeType!==void 0?this.I(z):J8(z)?this.H(z):this.L(z)}B(z){return this._$AA.parentNode.insertBefore(z,this._$AB)}I(z){this._$AH!==z&&(this._$AR(),this._$AH=this.B(z))}L(z){this._$AH!==B&&N(this._$AH)?this._$AA.nextSibling.data=z:this.I(M.createTextNode(z)),this._$AH=z}j(z){let{values:J,_$litType$:Z}=z,Q=typeof Z=="number"?this._$AC(z):(Z.el===void 0&&(Z.el=x.createElement(K0(Z.h,Z.h[0]),this.options)),Z);if(this._$AH?._$AD===Q)this._$AH.V(J);else{let Y=new I0(Q,this),F=Y.R(this.options);Y.V(J),this.I(F),this._$AH=Y}}_$AC(z){let J=w0.get(z.strings);return J===void 0&&w0.set(z.strings,J=new x(z)),J}H(z){s(this._$AH)||(this._$AH=[],this._$AR());let J=this._$AH,Z,Q=0;for(let Y of z)Q===J.length?J.push(Z=new u(this.B(k()),this.B(k()),this,this.options)):Z=J[Q],Z._$AI(Y),Q++;Q<J.length&&(this._$AR(Z&&Z._$AB.nextSibling,Q),J.length=Q)}_$AR(z=this._$AA.nextSibling,J){for(this._$AP?.(!1,!0,J);z!==this._$AB;){let Z=$0(z).nextSibling;$0(z).remove(),z=Z}}setConnected(z){this._$AM===void 0&&(this.D=z,this._$AP?.(z))}}class T{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(z,J,Z,Q,Y){this.type=1,this._$AH=B,this._$AN=void 0,this.element=z,this.name=J,this._$AM=Q,this.options=Y,Z.length>2||Z[0]!==""||Z[1]!==""?(this._$AH=Array(Z.length-1).fill(new String),this.strings=Z):this._$AH=B}_$AI(z,J=this,Z,Q){let Y=this.strings,F=!1;if(Y===void 0)z=A(this,z,J,0),F=!N(z)||z!==this._$AH&&z!==_,F&&(this._$AH=z);else{let q=z,j,$;for(z=Y[0],j=0;j<Y.length-1;j++)$=A(this,q[Z+j],J,j),$===_&&($=this._$AH[j]),F||=!N($)||$!==this._$AH[j],$===B?z=B:z!==B&&(z+=($??"")+Y[j+1]),this._$AH[j]=$}F&&!Q&&this.W(z)}W(z){z===B?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,z??"")}}class U0 extends T{constructor(){super(...arguments),this.type=3}W(z){this.element[this.name]=z===B?void 0:z}}class M0 extends T{constructor(){super(...arguments),this.type=4}W(z){this.element.toggleAttribute(this.name,!!z&&z!==B)}}class _0 extends T{constructor(z,J,Z,Q,Y){super(z,J,Z,Q,Y),this.type=5}_$AI(z,J=this){if((z=A(this,z,J,0)??B)===_)return;let Z=this._$AH,Q=z===B&&Z!==B||z.capture!==Z.capture||z.once!==Z.once||z.passive!==Z.passive,Y=z!==B&&(Z===B||Q);Q&&this.element.removeEventListener(this.name,this,Z),Y&&this.element.addEventListener(this.name,this,z),this._$AH=z}handleEvent(z){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,z):this._$AH.handleEvent(z)}}class A0{constructor(z,J,Z){this.element=z,this.type=6,this._$AN=void 0,this._$AM=J,this.options=Z}get _$AU(){return this._$AM._$AU}_$AI(z){A(this,z)}}var Q8=r.litHtmlPolyfillSupport;Q8?.(x,u),(r.litHtmlVersions??=[]).push("3.3.3");var Y8=(z,J,Z)=>{let Q=Z?.renderBefore??J,Y=Q._$litPart$;if(Y===void 0){let F=Z?.renderBefore??null;Q._$litPart$=Y=new u(J.insertBefore(k(),F),F,void 0,Z??{})}return Y._$AI(z),Y},t=globalThis;class R extends I{constructor(){super(...arguments),this.renderOptions={host:this},this.rt=void 0}createRenderRoot(){let z=super.createRenderRoot();return this.renderOptions.renderBefore??=z.firstChild,z}update(z){let J=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(z),this.rt=Y8(J,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this.rt?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this.rt?.setConnected(!1)}render(){return _}}R._$litElement$=!0,R.finalized=!0,t.litElementHydrateSupport?.({LitElement:R});var F8=t.litElementPolyfillSupport;F8?.({LitElement:R});(t.litElementVersions??=[]).push("4.2.2");var y0=g`
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
    .effect-label {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
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
      content: "";
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      width: 24px;
      pointer-events: none;
      background: linear-gradient(to left, var(--card-background-color), transparent);
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
    }
`;class O0 extends R{static properties={hass:{attribute:!1},_config:{state:!0}};setConfig(z){this._config={...z}}render(){return V`
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
    `}_entityChanged(z){let J=z.detail?.value??"",Z={...this._config,entity:J};this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:Z},bubbles:!0,composed:!0}))}static styles=g`
    .editor {
      padding: 8px;
    }
    .help {
      margin: 8px 0 0;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
  `}customElements.define("govee-led-ble-card-editor",O0);var L=15;function X(z,J,Z){return Math.max(J,Math.min(Z,z))}function D(z){let J=z.replace("#","");return[parseInt(J.slice(0,2),16),parseInt(J.slice(2,4),16),parseInt(J.slice(4,6),16)]}function p(z){return"#"+z.map((J)=>X(Math.round(J),0,255).toString(16).padStart(2,"0")).join("")}function h(z,J){if(z.length===0)throw Error("no stops");if(z.length===1){let $=z[0];return[$[0],$[1],$[2]]}let Z=z.length-1,Q=X(J,0,1)*Z,Y=X(Math.floor(Q),0,Z-1),F=Q-Y,q=z[Y],j=z[Y+1];return[q[0]+(j[0]-q[0])*F,q[1]+(j[1]-q[1])*F,q[2]+(j[2]-q[2])*F]}function q8(z){let J=Math.floor(z),Z=z-J;if(Z<0.5)return J;if(Z>0.5)return J+1;return J%2===0?J:J+1}function f(z,J=15){if(z.length===0)throw Error("no stops");if(J<=0)return[];if(z.length===1){let Z=z[0];return Array.from({length:J},()=>[Z[0],Z[1],Z[2]])}return Array.from({length:J},(Z,Q)=>{let Y=J>1?Q/(J-1):0;return h(z,Y).map(q8)})}function J0(z){let J=new Map,Z=[];return z.forEach((Q,Y)=>{let F=`${Q[0]},${Q[1]},${Q[2]}`,q=J.get(F);if(q===void 0)q={segments:[],rgb_color:[Q[0],Q[1],Q[2]]},J.set(F,q),Z.push(q);q.segments.push(Y+1)}),Z}var E0=[{id:"sunset",name:"Sunset",stops:[[255,89,94],[255,146,76],[255,202,58]]},{id:"ocean",name:"Ocean",stops:[[15,32,89],[25,130,196],[112,193,179]]},{id:"forest",name:"Forest",stops:[[27,67,50],[45,106,79],[149,213,178]]},{id:"rainbow",name:"Rainbow",stops:[[255,0,0],[255,183,0],[0,200,83],[0,145,234],[170,0,255]]},{id:"warm-white",name:"Warm white",stops:[[255,183,107]]},{id:"cool-white",name:"Cool white",stops:[[188,220,255]]}];function d0(z,J=15){return J0(f(z.stops,J))}function k0(z){return[...new Set(z)].sort((J,Z)=>J-Z)}function N0(z,J){let Z=Math.min(z,J),Q=Math.max(z,J),Y=new Set;for(let F=Z;F<=Q;F++)Y.add(F);return Y}function x0(z,J){let Z=new Set(z);if(Z.has(J))Z.delete(J);else Z.add(J);return Z}function u0(z=15){let J=new Set;for(let Z=1;Z<=z;Z++)J.add(Z);return J}function S(){return new Set}function T0(z){if(z===null||typeof z!=="object"||Array.isArray(z))return[];let J=[];for(let[Z,Q]of Object.entries(z)){if(typeof Q!=="string")continue;let Y=Q.trim();if(Y==="")continue;J.push({id:Z,name:Y})}return J.sort((Z,Q)=>{let Y=Z.name.toLowerCase(),F=Q.name.toLowerCase();if(Y!==F)return Y<F?-1:1;if(Z.id!==Q.id)return Z.id<Q.id?-1:1;return 0}),J}var y=[{id:"now",label:"Now"},{id:"studio",label:"Studio"},{id:"library",label:"Library"}];function Z0(z,J,Z){if(Z<=0)return z;switch(J){case"ArrowRight":case"ArrowDown":return(z+1)%Z;case"ArrowLeft":case"ArrowUp":return(z-1+Z)%Z;case"Home":return 0;case"End":return Z-1;default:return z}}var Q0=[{id:"static",label:"Static",available:!0},{id:"gradient",label:"Gradient",available:!0},{id:"sketch",label:"Sketch",available:!1},{id:"flat",label:"Flat",available:!1},{id:"combo",label:"Combo",available:!1}];function S0(z,J=null){let Z=J!==null&&J.some((Q)=>Q!==null);return{kind:"segments",colors:z.map((Q)=>Q===null?null:[Q[0],Q[1],Q[2]]),brightness:Z?J.map((Q)=>Q===null?null:Q):null}}function v0(z,J=null){return z.some((Z)=>Z!==null)||J!==null&&J.some((Z)=>Z!==null)}function b0(z){return{kind:"vibrant",stops:z.map((J)=>[J[0],J[1],J[2]])}}function z0(z){if(z!==null&&typeof z==="object"){let J=z.message;if(typeof J==="string"&&J.trim()!=="")return J}return null}function O(z,J="Something went wrong."){if(typeof z==="string"&&z.trim()!=="")return z;let Z=z0(z);if(Z!==null)return Z;if(z!==null&&typeof z==="object"){let Q=z,Y=z0(Q.error)??z0(Q.body);if(Y!==null)return Y}return J}var g0=["#ff595e","#ffca3a","#1982c4"],j8="#33cc66",Y0=2,F0=5,m0="Govee Effect Studio",l=Q0.filter((z)=>z.available),V8=Q0.filter((z)=>!z.available);function W8(z){if(!Array.isArray(z))return null;let J=[];for(let Z of z){if(!Array.isArray(Z)||Z.length<3)return null;let[Q,Y,F]=Z;if(typeof Q!=="number"||typeof Y!=="number"||typeof F!=="number")return null;J.push([Q,Y,F])}return J}class p0 extends R{static properties={hass:{attribute:!1},_config:{state:!0},_tab:{state:!0},_studioKind:{state:!0},_selection:{state:!0},_cursor:{state:!0},_paintColor:{state:!0},_staticColors:{state:!0},_stops:{state:!0},_studioStops:{state:!0},_dragStop:{state:!0},_dragFrac:{state:!0},_reduce:{state:!0},_effectName:{state:!0},_studioName:{state:!0},_renamingId:{state:!0},_renameValue:{state:!0},_deletingId:{state:!0},_feedback:{state:!0}};_dragging=!1;_dragAnchor=1;_raf=null;_t0=0;_mq;_ro;constructor(){super();this._tab="now",this._studioKind="static",this._selection=new Set,this._cursor=1,this._paintColor=j8,this._staticColors=Array.from({length:L},()=>null),this._stops=[...g0],this._studioStops=[...g0],this._dragStop=null,this._dragFrac=null,this._reduce=!1,this._effectName="",this._studioName="",this._renamingId=null,this._renameValue="",this._deletingId=null,this._feedback=null}static getStubConfig(z){return{entity:(z?Object.keys(z.states).find((Z)=>Z.startsWith("light.")&&Array.isArray(z.states[Z].attributes?.segment_colors)):void 0)??""}}static getConfigElement(){return document.createElement("govee-led-ble-card-editor")}setConfig(z){if(!z)throw Error("Invalid configuration");this._config={...z}}getCardSize(){return 12}connectedCallback(){super.connectedCallback();let z=window.matchMedia("(prefers-reduced-motion: reduce)");this._reduce=z.matches,this._mq=z,z.addEventListener("change",this._onReduceChange),this._ro=new ResizeObserver(()=>this._updateClipped()),this._ro.observe(this),this._raf=requestAnimationFrame((J)=>this._tick(J))}disconnectedCallback(){if(super.disconnectedCallback(),this._raf!==null)cancelAnimationFrame(this._raf);this._raf=null,this._mq?.removeEventListener("change",this._onReduceChange),this._ro?.disconnect(),window.removeEventListener("pointermove",this._onMove),window.removeEventListener("pointerup",this._onUp),window.removeEventListener("pointermove",this._onStopMove),window.removeEventListener("pointerup",this._onStopUp)}updated(){this._updateClipped()}_updateClipped(){for(let z of this.renderRoot.querySelectorAll(".strip-scroll"))z.classList.toggle("clipped",z.scrollWidth>z.clientWidth+1)}_onReduceChange=(z)=>{this._reduce=z.matches};_selectTab(z){if(this._tab===z)return;this._tab=z,this._selection=S(),this._cursor=1}_onTabKey(z){let J=y.findIndex((Q)=>Q.id===this._tab),Z=Z0(J,z.key,y.length);if(Z===J)return;z.preventDefault(),this._selectTab(y[Z].id),this.updateComplete.then(()=>{this.renderRoot.querySelector(`#tab-${y[Z].id}`)?.focus()})}_selectKind(z){this._studioKind=z}_onKindKey(z){let J=l.findIndex((Q)=>Q.id===this._studioKind),Z=Z0(J,z.key,l.length);if(Z===J)return;z.preventDefault(),this._studioKind=l[Z].id,this.updateComplete.then(()=>{this.renderRoot.querySelector('.kinds .kind[aria-checked="true"]')?.focus()})}_segmentColors(){let z=this._config?.entity;if(!z||!this.hass)return null;let J=this.hass.states[z];if(!J)return null;return W8(J.attributes?.segment_colors)}_cellFromClientX(z){let J=this.renderRoot.querySelector(".strip");if(!J)return 1;let Z=J.getBoundingClientRect(),Q=Z.width/L;return X(Math.floor((z-Z.left)/Q),0,L-1)+1}_onDown(z){z.preventDefault(),this._dragging=!0,this._dragAnchor=this._cellFromClientX(z.clientX),this._cursor=this._dragAnchor,this._selection=new Set([this._dragAnchor]),this.renderRoot.querySelector(".strip")?.focus(),window.addEventListener("pointermove",this._onMove),window.addEventListener("pointerup",this._onUp)}_onMove=(z)=>{if(!this._dragging)return;let J=this._cellFromClientX(z.clientX);this._selection=N0(this._dragAnchor,J),this._cursor=J};_onUp=()=>{this._dragging=!1,window.removeEventListener("pointermove",this._onMove),window.removeEventListener("pointerup",this._onUp)};_onKey(z){let J=z.key,Z=["ArrowRight","ArrowDown","ArrowLeft","ArrowUp","Home","End"];if(J==="ArrowRight"||J==="ArrowDown")this._cursor=X(this._cursor+1,1,L),z.preventDefault();else if(J==="ArrowLeft"||J==="ArrowUp")this._cursor=X(this._cursor-1,1,L),z.preventDefault();else if(J==="Home")this._cursor=1,z.preventDefault();else if(J==="End")this._cursor=L,z.preventDefault();else if(J===" "||J==="Spacebar")this._selection=x0(this._selection,this._cursor),z.preventDefault();else if(J==="Enter"){if(this._tab==="studio")this._paintStatic();else this._applyPaint();z.preventDefault()}else if(J==="Escape")this._dragging=!1,this._selection=S(),z.preventDefault();if(Z.includes(J))this._scrollCursorIntoView()}_scrollCursorIntoView(){this.updateComplete.then(()=>{this.renderRoot.querySelector(".cell.cursor")?.scrollIntoView({inline:"nearest",block:"nearest"})})}_selectAll(){this._selection=u0(L)}_clear(){this._selection=S()}_applyPaint(){let z=this._config?.entity;if(!this.hass||!z||this._selection.size===0)return;let J=[{segments:k0(this._selection),rgb_color:D(this._paintColor)}];this.hass.callService("ha_govee_led_ble","paint_segments",{groups:J},{entity_id:z})}_paintStatic(){if(this._selection.size===0)return;let z=[...this._staticColors];for(let J of this._selection)z[J-1]=this._paintColor;this._staticColors=z}_setUnchangedStatic(){if(this._selection.size===0)return;let z=[...this._staticColors];for(let J of this._selection)z[J-1]=null;this._staticColors=z}_resetStatic(){this._staticColors=Array.from({length:L},()=>null),this._selection=S()}_activeStops(){return this._tab==="studio"?this._studioStops:this._stops}_setActiveStops(z){if(this._tab==="studio")this._studioStops=z;else this._stops=z}_addStop(){let z=this._activeStops();if(z.length>=F0)return;let J=h(z.map(D),0.5);this._setActiveStops([...z,p(J)])}_removeStop(z){let J=this._activeStops();if(J.length<=Y0)return;this._setActiveStops(J.filter((Z,Q)=>Q!==z))}_recolourStop(z,J){let Z=[...this._activeStops()];Z[z]=J,this._setActiveStops(Z)}_stopTargetIndex(z){let J=this.renderRoot.querySelector(".gradient-bar"),Z=this._activeStops();if(!J)return this._dragStop??0;let Q=J.getBoundingClientRect(),Y=X((z-Q.left)/Q.width,0,1);return X(Math.round(Y*(Z.length-1)),0,Z.length-1)}_startStopDrag(z,J){z.preventDefault(),this._dragStop=J,window.addEventListener("pointermove",this._onStopMove),window.addEventListener("pointerup",this._onStopUp)}_onStopMove=(z)=>{if(this._dragStop===null)return;let J=this.renderRoot.querySelector(".gradient-bar");if(!J)return;let Z=J.getBoundingClientRect();this._dragFrac=X((z.clientX-Z.left)/Z.width,0,1)};_onStopUp=(z)=>{if(this._dragStop===null)return;let J=this._dragStop,Z=this._stopTargetIndex(z.clientX);if(J!==Z){let Q=[...this._activeStops()],[Y]=Q.splice(J,1);Q.splice(Z,0,Y),this._setActiveStops(Q)}this._dragStop=null,this._dragFrac=null,window.removeEventListener("pointermove",this._onStopMove),window.removeEventListener("pointerup",this._onStopUp)};_applyGradient(){let z=this._config?.entity;if(!this.hass||!z)return;let J=J0(f(this._stops.map(D),L));this.hass.callService("ha_govee_led_ble","paint_segments",{groups:J},{entity_id:z})}_applyPreset(z){let J=this._config?.entity;if(!this.hass||!J)return;this.hass.callService("ha_govee_led_ble","paint_segments",{groups:d0(z)},{entity_id:J})}_presetSwatch(z){if(z.length===1){let[Z,Q,Y]=z[0];return`rgb(${Z},${Q},${Y})`}return`linear-gradient(90deg, ${z.map(([Z,Q,Y],F)=>`rgb(${Z},${Q},${Y}) ${F/(z.length-1)*100}%`).join(", ")})`}async _saveCurrent(){let z=this._config?.entity;if(!this.hass||!z)return;let J=this._effectName.trim();try{await this.hass.callService("ha_govee_led_ble","save_effect",{name:J,capture_current:!0},{entity_id:z}),this._effectName="",this._feedback={kind:"info",text:`Saved "${J}".`}}catch(Z){this._feedback={kind:"error",text:O(Z)}}}async _saveStudio(){let z=this._config?.entity;if(!this.hass||!z)return;let J=this._studioName.trim(),Z=this._studioKind==="static"?S0(this._staticColors.map((Q)=>Q===null?null:D(Q))):b0(this._studioStops.map(D));try{await this.hass.callService("ha_govee_led_ble","save_effect",{name:J,content:Z},{entity_id:z}),this._studioName="",this._feedback={kind:"info",text:`Saved "${J}".`}}catch(Q){this._feedback={kind:"error",text:O(Q)}}}async _applyEffect(z){let J=this._config?.entity;if(!this.hass||!J)return;this._feedback=null;try{await this.hass.callService("light","turn_on",{effect:z.name},{entity_id:J})}catch(Z){this._feedback={kind:"error",text:O(Z)}}}_startRename(z){this._feedback=null,this._deletingId=null,this._renamingId=z.id,this._renameValue=z.name,this.updateComplete.then(()=>{let J=this.renderRoot.querySelector(".rename-input");J?.focus(),J?.select()})}_cancelRename(){this._renamingId=null,this._renameValue=""}async _commitRename(z){let J=this._config?.entity;if(!this.hass||!J)return;let Z=this._renameValue.trim();try{await this.hass.callService("ha_govee_led_ble","rename_effect",{id:z.id,to:Z},{entity_id:J}),this._renamingId=null,this._renameValue="",this._feedback={kind:"info",text:`Renamed to "${Z}".`}}catch(Q){this._feedback={kind:"error",text:O(Q)}}}_askDelete(z){if(this._feedback=null,this._renamingId===z.id)this._cancelRename();this._deletingId=z.id,this.updateComplete.then(()=>{this.renderRoot.querySelector(".confirm-cancel")?.focus()})}_cancelDelete(){this._deletingId=null}_onDeleteKey(z){if(z.key==="Escape")z.preventDefault(),this._cancelDelete()}async _deleteEffect(z){let J=this._config?.entity;if(!this.hass||!J)return;this._deletingId=null;try{await this.hass.callService("ha_govee_led_ble","delete_effect",{id:z.id},{entity_id:J}),this._feedback={kind:"info",text:`Deleted "${z.name}".`}}catch(Z){this._feedback={kind:"error",text:O(Z)}}}_onSaveKey(z,J){if(z.key==="Enter")z.preventDefault(),J()}_onRenameKey(z,J){if(z.key==="Enter")z.preventDefault(),this._commitRename(J);else if(z.key==="Escape")z.preventDefault(),this._cancelRename()}_tick(z){if(!this._t0)this._t0=z;let J=this.renderRoot?.querySelector("canvas.preview");if(J)this._draw(J,(z-this._t0)/1000);this._raf=requestAnimationFrame((Z)=>this._tick(Z))}_draw(z,J){let Z=window.devicePixelRatio||1,Q=z.clientWidth||480,Y=z.clientHeight||44;if(z.width!==Math.round(Q*Z))z.width=Math.round(Q*Z),z.height=Math.round(Y*Z);let F=z.getContext("2d");if(!F)return;F.setTransform(Z,0,0,Z,0,0),F.clearRect(0,0,Q,Y);let q=this._stops.map(D),j=L,$=this._reduce?0:J*0.25,C=3,W=(Q-C*(j-1))/j;for(let H=0;H<j;H++){let P=this._reduce?H/(j-1):((H/j+$)%1+1)%1,w=h(q,P);F.fillStyle=`rgb(${w.map((f0)=>Math.round(f0)).join(",")})`;let h0=H*(W+C);F.beginPath(),F.roundRect(h0,0,W,Y,4),F.fill()}}render(){if(!this._config)return B;let z=this._config.entity;if(!z)return this._notice("Select a light entity in the card configuration.");let J=this.hass?.states?.[z];if(!J||J.state==="unavailable"||J.state==="unknown")return this._notice(`${z} is unavailable.`);let Z=this._segmentColors();if(!Z)return this._notice(`${z} exposes no segment colours; this model has no addressable segments.`);return V`
      <ha-card>
        ${this._renderHeader(J)}
        <div class="body">
          ${this._tab==="now"?this._renderNow(Z):B}
          ${this._tab==="studio"?this._renderStudio():B}
          ${this._tab==="library"?this._renderLibrary(J):B}
        </div>
      </ha-card>
    `}_notice(z){return V`
      <ha-card header=${m0}>
        <div class="notice">${z}</div>
      </ha-card>
    `}_renderHeader(z){let J=typeof z.attributes?.effect==="string"&&z.attributes.effect!==""?z.attributes.effect:z.state==="on"?"Colour":"Off";return V`
      <div class="card-head">
        <div class="title">${m0}</div>
        <div class="status">
          <span>Current:</span>
          <span class="current">${J}</span>
        </div>
        <div class="tabs" role="tablist" aria-label="Effect Studio sections">
          ${y.map((Z)=>V`
              <button
                class="tab ${this._tab===Z.id?"active":""}"
                id=${`tab-${Z.id}`}
                role="tab"
                aria-selected=${this._tab===Z.id?"true":"false"}
                aria-controls=${`panel-${Z.id}`}
                tabindex=${this._tab===Z.id?"0":"-1"}
                @click=${()=>this._selectTab(Z.id)}
                @keydown=${this._onTabKey}
              >
                ${Z.label}
              </button>
            `)}
        </div>
        ${this._feedback?V`<div class="feedback ${this._feedback.kind}" role="alert">
              ${this._feedback.text}
            </div>`:B}
      </div>
    `}_renderScopeBand(z){return V`
      <div class="scope-band ${z}" role="note">
        <span class="dot" aria-hidden="true"></span>
        <span>${z==="live"?"Applies to the strip — changes show instantly":"Draft — builds a saved effect and never changes the strip"}</span>
      </div>
    `}_renderNow(z){let J=Array.from({length:L},(Z,Q)=>{let Y=z[Q];return Y?p(Y):null});return V`
      <div id="panel-now" role="tabpanel" aria-labelledby="tab-now">
        ${this._renderScopeBand("live")}
        <section>
          <div class="row heading">
            <span class="label">Segment painter</span>
            <span class="hint">${this._selection.size} selected</span>
          </div>
          ${this._renderStrip(J,"off")}
          <div class="row controls">
            <input
              type="color"
              aria-label="Paint colour"
              .value=${this._paintColor}
              @input=${(Z)=>this._paintColor=Z.target.value}
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
    `}_renderStrip(z,J){let Z=[];for(let Q=1;Q<=L;Q++){let Y=z[Q-1]??null,F=this._selection.has(Q),q=Q===this._cursor,j=Y?"painted":J==="off"?"off":"unchanged";Z.push(V`
        <div
          class="cell ${F?"sel":""} ${q?"cursor":""} ${Y?"":J}"
          style=${Y?`background:${Y}`:""}
          role="option"
          aria-selected=${F?"true":"false"}
          aria-label=${`Segment ${Q}, ${j}`}
          title=${`Segment ${Q}`}
        >
          <span class="cell-num">${Q}</span>
        </div>
      `)}return V`
      <div class="strip-scroll">
        <div
          class="strip"
          style="grid-template-columns: repeat(${L}, 1fr)"
          tabindex="0"
          role="listbox"
          aria-multiselectable="true"
          aria-label=${`Segment painter, ${L} segments`}
          @pointerdown=${this._onDown}
          @keydown=${this._onKey}
        >
          ${Z}
        </div>
      </div>
    `}_renderGradient(){return V`
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
    `}_renderStopEditor(){let z=this._activeStops(),J=z.length,Z=`linear-gradient(90deg, ${z.map((Q,Y)=>`${Q} ${Y/(J-1)*100}%`).join(", ")})`;return V`
      <div class="row heading">
        <span class="label">Gradient stops</span>
        <span class="hint">${J} of ${Y0} to ${F0}</span>
      </div>
      <div class="gradient-track">
        <div class="gradient-bar" style="background:${Z}">
          ${z.map((Q,Y)=>V`
              <div
                class="handle ${this._dragStop===Y?"dragging":""}"
                style="left:${this._dragStop===Y&&this._dragFrac!==null?this._dragFrac*100:Y/(J-1)*100}%;background:${Q}"
                @pointerdown=${(F)=>this._startStopDrag(F,Y)}
                title=${`Stop ${Y+1}`}
              ></div>
            `)}
        </div>
      </div>
      <div class="stops">
        ${z.map((Q,Y)=>V`
            <div class="stop">
              <input
                type="color"
                aria-label=${`Stop ${Y+1} colour`}
                .value=${Q}
                @input=${(F)=>this._recolourStop(Y,F.target.value)}
              />
              <button
                class="btn tiny"
                ?disabled=${J<=Y0}
                @click=${()=>this._removeStop(Y)}
                aria-label=${`Remove stop ${Y+1}`}
                title="Remove stop"
              >
                &times;
              </button>
            </div>
          `)}
        <button
          class="btn tiny add"
          ?disabled=${J>=F0}
          @click=${this._addStop}
          aria-label="Add stop"
          title="Add stop"
        >
          +
        </button>
      </div>
    `}_renderPresets(){return V`
      <section>
        <div class="row heading">
          <span class="label">Presets</span>
        </div>
        <div class="row presets">
          ${E0.map((z)=>V`
              <button
                class="preset"
                @click=${()=>this._applyPreset(z)}
                title=${z.name}
                aria-label=${z.name}
              >
                <span
                  class="swatch"
                  style="background:${this._presetSwatch(z.stops)}"
                ></span>
                <span class="preset-name">${z.name}</span>
              </button>
            `)}
        </div>
      </section>
    `}_renderSaveCurrent(){return V`
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
            @input=${(z)=>this._effectName=z.target.value}
            @keydown=${(z)=>this._onSaveKey(z,()=>void this._saveCurrent())}
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
    `}_renderStudio(){return V`
      <div id="panel-studio" role="tabpanel" aria-labelledby="tab-studio">
        ${this._renderScopeBand("draft")}
        <section>
          <div class="row heading">
            <span class="label">Effect kind</span>
          </div>
          <div class="kinds" role="radiogroup" aria-label="Effect kind" @keydown=${this._onKindKey}>
            ${l.map((z)=>V`
                <button
                  class="kind ${this._studioKind===z.id?"active":""}"
                  role="radio"
                  aria-checked=${this._studioKind===z.id?"true":"false"}
                  tabindex=${this._studioKind===z.id?"0":"-1"}
                  @click=${()=>this._selectKind(z.id)}
                >
                  ${z.label}
                </button>
              `)}
          </div>
          <div class="kinds-soon">
            <span>Coming next:</span>
            ${V8.map((z)=>V`
                <button class="kind soon" disabled aria-disabled="true">
                  ${z.label}<span class="soon-tag">soon</span>
                </button>
              `)}
          </div>
        </section>
        ${this._studioKind==="gradient"?this._renderGradientAuthor():this._renderStaticEditor()}
      </div>
    `}_renderStaticEditor(){let z=this._staticColors.filter((Z)=>Z!==null).length,J=v0(this._staticColors.map((Z)=>Z===null?null:D(Z)));return V`
      <section>
        <div class="row heading">
          <span class="label">Static segments</span>
          <span class="hint">${z} painted · ${this._selection.size} selected</span>
        </div>
        ${this._renderStrip(this._staticColors,"unchanged")}
        <div class="row controls">
          <input
            type="color"
            aria-label="Paint colour"
            .value=${this._paintColor}
            @input=${(Z)=>this._paintColor=Z.target.value}
          />
          <button class="btn primary" @click=${this._paintStatic}>Paint selected</button>
          <button class="btn" @click=${this._setUnchangedStatic}>Clear selected</button>
          <button class="btn" @click=${this._selectAll}>Select all</button>
          <button class="btn" @click=${this._resetStatic}>Reset</button>
        </div>
        <p class="help">
          Paint a colour onto chosen segments; hatched segments are left as they are on the strip.
        </p>
        ${this._renderStudioSave(J,"Paint at least one segment to save.")}
      </section>
    `}_renderGradientAuthor(){let z=f(this._studioStops.map(D),L).map(p);return V`
      <section>
        ${this._renderStopEditor()}
        <div class="row heading">
          <span class="label">Draft preview · ${L} segments</span>
        </div>
        ${this._renderPreviewStrip(z)}
        <p class="help">Saves the colour stops as a gradient effect.</p>
        ${this._renderStudioSave(!0,"")}
      </section>
    `}_renderPreviewStrip(z){return V`
      <div class="strip-scroll">
        <div
          class="strip preview-strip"
          style="grid-template-columns: repeat(${L}, 1fr)"
          aria-hidden="true"
        >
          ${z.map((J,Z)=>V`
              <div class="cell" style="background:${J}" title=${`Segment ${Z+1}`}>
                <span class="cell-num">${Z+1}</span>
              </div>
            `)}
        </div>
      </div>
    `}_renderStudioSave(z,J){let Z=this._studioName.trim()!=="";return V`
      <div class="row controls">
        <input
          class="effect-name"
          type="text"
          aria-label="Effect name"
          placeholder="Name this effect"
          .value=${this._studioName}
          @input=${(Q)=>this._studioName=Q.target.value}
          @keydown=${(Q)=>this._onSaveKey(Q,()=>void this._saveStudio())}
        />
        <button
          class="btn primary"
          ?disabled=${!Z||!z}
          @click=${this._saveStudio}
        >
          Save effect
        </button>
      </div>
      ${!z&&J!==""?V`<p class="help">${J}</p>`:B}
    `}_renderLibrary(z){let J=T0(z.attributes?.custom_effects),Z=typeof z.attributes?.effect==="string"?z.attributes.effect:null;return V`
      <div id="panel-library" role="tabpanel" aria-labelledby="tab-library">
        <section>
          <div class="row heading">
            <span class="label">Saved effects</span>
            <span class="hint">${J.length} saved</span>
          </div>
          ${J.length===0?V`<p class="help">
                No custom effects saved yet. Create one in the Studio tab, or snapshot the strip from
                the Now tab.
              </p>`:V`
                <p class="help">Select an effect to apply it.</p>
                <ul class="effects" role="list">
                  ${J.map((Q)=>this._renderEffectRow(Q,Z))}
                </ul>
              `}
        </section>
      </div>
    `}_renderEffectRow(z,J){if(this._renamingId===z.id)return V`
        <li class="effect renaming">
          <input
            class="effect-name rename-input"
            type="text"
            aria-label=${`New name for ${z.name}`}
            .value=${this._renameValue}
            @input=${(Q)=>this._renameValue=Q.target.value}
            @keydown=${(Q)=>this._onRenameKey(Q,z)}
          />
          <button class="btn primary" @click=${()=>this._commitRename(z)}>
            Save
          </button>
          <button class="btn" @click=${this._cancelRename}>Cancel</button>
        </li>
      `;if(this._deletingId===z.id)return V`
        <li class="effect">
          <span class="confirm-text">Delete "${z.name}"?</span>
          <button
            class="btn confirm-cancel"
            @click=${this._cancelDelete}
            @keydown=${this._onDeleteKey}
          >
            Cancel
          </button>
          <button
            class="btn danger primary"
            @click=${()=>this._deleteEffect(z)}
            @keydown=${this._onDeleteKey}
          >
            Delete
          </button>
        </li>
      `;let Z=J!==null&&J===z.name;return V`
      <li class="effect ${Z?"active":""}">
        ${Z?V`<span class="badge-active" aria-current="true">✓ Active</span>`:V`<button
              class="btn primary"
              @click=${()=>this._applyEffect(z)}
              aria-label=${`Apply ${z.name}`}
            >
              Apply
            </button>`}
        <span class="effect-label" title=${z.name}>${z.name}</span>
        <button
          class="btn"
          @click=${()=>this._startRename(z)}
          aria-label=${`Rename ${z.name}`}
        >
          Rename
        </button>
        <button
          class="btn danger"
          @click=${()=>this._askDelete(z)}
          aria-label=${`Delete ${z.name}`}
        >
          Delete
        </button>
      </li>
    `}static styles=y0}customElements.define("govee-led-ble-card",p0);window.customCards=window.customCards||[];window.customCards.push({type:"govee-led-ble-card",name:"Govee LED BLE",description:"Paint, compose and save custom effects for a segment-capable Govee LED BLE light.",preview:!1});console.info("%c govee-led-ble-card ","background:#1982c4;color:#fff;border-radius:3px","loaded");
