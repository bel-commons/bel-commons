/**
 * This JS file controls and connect the network to the PyBEL-web API.
 *
 * @summary   Network controller of PyBEL-web explorer
 *
 * @requires jquery, d3, d3-context-menu, inspire-tree, blob
 *
 */


// Constants used in the graph controller
const nominalBaseNodeSize = 10; // Default node radius
var edgeStroke = 3.5;  // Edge width
var minZoom = 0.1, maxZoom = 10; // Zoom variables

// The maximum number of nodes that can be rendered in the explorer
const maximumNodesToRender = 1500;

/**
 * Spinner on Ajax call
 */
$body = $("body");

$(document).on({
    ajaxStart: function () {
        $body.addClass("loading");
    },
    ajaxStop: function () {
        $body.removeClass("loading");
    },
    ajaxError: function () {
        $body.removeClass("loading");
        alert("An error occurred. Please reload the page.");
    }
});

/**
 * Returns a random integer between min (inclusive) and max (inclusive)
 * Using Math.round() will give you a non-uniform distribution!
 * @param {int} min
 * @param {int} max
 * @return {int}
 */
function getRandomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}


/**
 * Returns object with selected nodes in tree
 * @param {InspireTree} tree
 * @returns {object} selected nodes in the tree
 */
function getSelectedNodesFromTree(tree) {
    var selectedNodes = tree.selected(true);

    var selectionHashMap = {};

    selectedNodes.forEach(function (nodeObject) {

        var key = nodeObject.text.toString();

        selectionHashMap[key] = nodeObject.children.map(function (child) {
            return child.text
        });
    });

    return selectionHashMap;
}


function handleHgncNodeInfo(nodeObject, data) {
    if (data.identifier) {
        nodeObject['HGNC Identifier'] = data.identifier
    }
    if (data.symbol) {
        nodeObject['HGNC Symbol'] = data.symbol
    }
    if (data.name) {
        nodeObject['HGNC Name'] = data.name
    }
    if (data.locus_group) {
        nodeObject['HGNC Locus Group'] = data.locus_group
    }
    if (data.locus_type) {
        nodeObject['HGNC Locus Type'] = data.locus_type
    }
}

function handleEntrezNodeInfo(nodeObject, data) {
    if (data.entrez_id) {
        nodeObject['Entrez Identifier'] = data.entrez_id
    }
    if (data.name) {
        nodeObject['Entrez Name'] = data.name
    }
    if (data.species) {
        nodeObject['Entrez Species'] = data.species
    }
    if (data.description) {
        nodeObject['Entrez Description'] = data.description
    }
    if (data.type) {
        nodeObject['Entrez Type'] = data.type
    }
}

function handleChebiNodeInfo(nodeObject, data) {
    if (data.chebi_id) {
        nodeObject['ChEBI Identifier'] = data.chebi_id
    }
    if (data.name) {
        nodeObject['ChEBI Name'] = data.name
    }
    if (data.definition) {
        nodeObject['ChEBI Definition'] = data.definition
    }
    if (data.inchi) {
        nodeObject['ChEBI InChI'] = data.inchi
    }
    if (data.source) {
        nodeObject['ChEBI Source'] = data.source
    }
}

function handleExpasyNodeInfo(nodeObject, data) {
    if (data.expasy_id) {
        nodeObject['ExPASy Identifier'] = data.expasy_id
    }
    if (data.description) {
        nodeObject['ExPASy Description'] = data.description
    }
}

function handleGoNodeInfo(nodeObject, data) {
    if (data.go_id) {
        nodeObject['GO Identifier'] = data.go_id
    }
    if (data.name) {
        nodeObject['GO Name'] = data.name
    }
    if (data.namespace) {
        nodeObject['GO Namespace'] = data.namespace
    }
    if (data.description) {
        nodeObject['GO Definition'] = data.definition
    }
}

function handleMeshNodeInfo(nodeObject, data) {
    if (data.descriptor_ui) {
        nodeObject['MeSH Descriptor UI'] = data.descriptor_ui
    }
    if (data.descriptor_name) {
        nodeObject['MeSH Descriptor Name'] = data.descriptor_name
    }
    if (data.concept_ui) {
        nodeObject['MeSH Concept UI'] = data.concept_ui
    }
    if (data.concept_name) {
        nodeObject['MeSH Concept Name'] = data.concept_name
    }
    if (data.term_ui) {
        nodeObject['MeSH Term UI'] = data.term_ui
    }
    if (data.term_name) {
        nodeObject['MeSH Term Name'] = data.term_name
    }
}

function handleNodeResponseCommon(nodeObject, node) {
    if (node.identifier) {
        nodeObject["Identifier"] = node.identifier;
    }
    if (node.label) {
        nodeObject["Label"] = node.label
    }
    if (node.description) {
        nodeObject["Description"] = node.description
    }
}

function handleNodeResponse(nodeObject, nodeResponse) {
    if (nodeResponse && nodeResponse.annotations) {
        // TODO use microservices for this instead of asking the main application
        if (nodeResponse.annotations.HGNC) {
            handleHgncNodeInfo(nodeObject, nodeResponse.annotations.HGNC)
        }
        if (nodeResponse.annotations.ENTREZ) {
            handleEntrezNodeInfo(nodeObject, nodeResponse.annotations.ENTREZ)
        }
        if (nodeResponse.annotations.CHEBI) {
            handleChebiNodeInfo(nodeObject, nodeResponse.annotations.CHEBI)
        }
        if (nodeResponse.annotations.EXPASY) {
            handleExpasyNodeInfo(nodeObject, nodeResponse.annotations.EXPASY)
        }
        if (nodeResponse.annotations.GO) {
            handleGoNodeInfo(nodeObject, nodeResponse.annotations.GO)
        }
        if (nodeResponse.annotations.MESH) {
            handleMeshNodeInfo(nodeObject, nodeResponse.annotations.MESH)
        }
    }
}

function updateDynamicTable(dynamicTable, nodeObject) {
    var row = 0;
    $.each(nodeObject, function (key, value) {
        insertRow(dynamicTable, row, key, value);
        row++
    });
}

/**
 * Renders node info table
 * @param {object} node object
 */
function displayNodeInfo(node) {

    var dynamicTable = document.getElementById('info-table');

    while (dynamicTable.rows.length > 0) {
        dynamicTable.deleteRow(0);
    }

    const url = "/api/node/" + node.id;

    var nodeObject = {};

    nodeObject["BEL"] = '<a target="_blank" href="/node/' + node.id + '"><code>' + node.bel + "</code> <span class=\"glyphicon glyphicon-new-window\"></span></a>";

    $.ajax({
        type: "GET",
        url: url,
        dataType: "json",
        global: false,
        error: function (request) {
            console.log('unable to look up node ' + node.id);
            handleNodeResponseCommon(nodeObject, node);
            updateDynamicTable(dynamicTable, nodeObject);
        },
        success: function (nodeResponse) {
            handleNodeResponseCommon(nodeObject, node);
            handleNodeResponse(nodeObject, nodeResponse);
            updateDynamicTable(dynamicTable, nodeObject);
        }
    });
}


/**
 * Gets the best name for a node object
 * @param {object} node_data object
 */
function getCanonicalName(node_data) {
    if (node_data.cname) {
        return node_data.cname;
    } else if (node_data.name) {
        return node_data.name
    } else if (node_data.bel) {
        return node_data.bel
    } else {
        console.log('Undefined node: ' + node_data);
        return 'UNDEFINED'
    }
}

/**
 * Renders edge info table
 * @param {object} edge object
 */
function displayEdgeInfo(edge) {

    var edgeObject = {};

    edgeObject["Links"] = '<ul class="list-inline">';
    edgeObject["Links"] += '<li><a target="_blank" class="btn btn-default" href="/node/' + edge.source.id + '"><code>' + getCanonicalName(edge.source) + '</code> <span class="glyphicon glyphicon-new-window"></span></a></li>';
    edgeObject["Links"] += '<li><a target="_blank" class="btn btn-default" href="/node/' + edge.target.id + '"><code>' + getCanonicalName(edge.target) + '</code> <span class="glyphicon glyphicon-new-window"></span></a></li>';
    edgeObject["Links"] += '<li><a target="_blank" class="btn btn-default" href="/node/' + edge.source.id + '/edges/' + edge.target.id + '">All Evidences <span class="glyphicon glyphicon-new-window"></span></a></li>';
    edgeObject["Links"] += '</ul>';

    if (edge.contexts) {
        $.each(edge.contexts, function (key, context) {

                const sk = context.id.slice(0, 10);
                edgeObject[sk] = '<dl class="dl-horizontal">';
                edgeObject[sk] += '<dt>BEL</dt><dd><code>' + context.bel + '</code></dd>';

                if (context.citation) {
                    edgeObject[sk] += '<dt>Citation</dt><dd>';
                    if (context.citation.type === "PubMed") {
                        edgeObject[sk] += '<a target="_blank" href="https://www.ncbi.nlm.nih.gov/pubmed/' + context.citation.reference + '" style="text-decoration: underline">PMID:' + context.citation.reference + ' <span class="glyphicon glyphicon-new-window"></a> | <a target="_blank" href="/citation/pubmed/' +
                            context.citation.reference + '">See More Statements <span class="glyphicon glyphicon-search" aria-hidden="true"></span></a>';
                    } else if (context.citation.type === "URL") {
                        edgeObject[sk] += '<a target="_blank" href=' + context.citation.reference + " target='_blank' " +
                            "style='text-decoration: underline'>" + context.citation.reference + "</a>";
                    } else {
                        // TODO handle DOIs?
                        edgeObject[sk] += context.citation.reference;
                    }

                    // TODO add link to all edges from that citation

                    edgeObject[sk] += '</dd>';
                }

                if (context.evidence) {
                    edgeObject[sk] += '<dt>Support</dt><dd>' + context.evidence + "</dd>";
                }

                if (context.annotations && Object.keys(context.annotations).length > 0) {
                    $.each(context.annotations, function (annotation_key, annotation_values) {
                        $.each(annotation_values, function (annotation_value) {
                            edgeObject[sk] += '<dt>' + annotation_key + '</dt><dd>' + annotation_value + '</dd>';
                        });
                    });
                }

                if (window.allow_voting === true) {
                    edgeObject[sk] += '<dt>Links</dt><dd><a target="_blank" href="/edge/' + context.id + '">' + 'More Information</a> ';
                    edgeObject[sk] += 'or <a href="#" data-toggle="modal" data-target="#edge-feedback" data-edge="' +
                        context.id + '">Give Feedback</a>';
                    edgeObject[sk] += '</dd>';
                }

                edgeObject[sk] += '</dl>';
            }
        );
    }

    var dynamicTable = document.getElementById('info-table');

    while (dynamicTable.rows.length > 0) {
        dynamicTable.deleteRow(0);
    }

    var row = 0;
    $.each(edgeObject, function (sk, column1) {
        var row = dynamicTable.insertRow(row);
        var cell1 = row.insertCell(0);
        cell1.innerHTML = column1;
        row++
    });
}


/**
 * Renders query info table
 * @param {object} query result returned by the query info endpoint
 */
function displayQueryInfo(query) {
    var dynamicTable = document.getElementById('query-table');

    while (dynamicTable.rows.length > 0) {
        dynamicTable.deleteRow(0);
    }

    var queryObject = {};

    queryObject["Identifier"] = query.id;

    if (query.creator) {
        queryObject["Creator"] = query.creator;
    }
    queryObject["Assembly"] = query.networks.join(", ");

    if (query.seeding && query.seeding.length !== 0) {
        queryObject["Seeding"] = query.seeding.map(function (object) {
            if (object.type === "annotation") {
                var arr = [];

                if (object.data.or === true) {
                    var queryType = "Any of the annotations are present in a given edge"
                } else {
                    var queryType = "All of the annotations are present in a given edge"
                }

                for (var key in object.data.annotations) {
                    if (object.data.annotations.hasOwnProperty(key)) {
                        arr.push(key + '=' + object.data.annotations[key]);
                    }
                }
                return object.type + ": [" + arr.join(',') + "] " + queryType;
            } else if (object.type === 'sample') {
                return object.type + ': [seed=' + object.data.seed + ']';
            }

            return object.type + ": [" + object.data + "]";
        });
    }

    if (query.pipeline && query.pipeline.length !== 0) {
        queryObject["Pipeline"] = '<ol class="query-box-pipeline">';
        $.each(query.pipeline, function (query_index, query_value) {
            queryObject["Pipeline"] += '<li>' + query_value.function.replace(/_/g, ' ') + '</li>';
        });
        queryObject["Pipeline"] += '</ol>';
    }

    var row = 0;
    $.each(queryObject, function (key, value) {
        insertRow(dynamicTable, row, key, value);
        row++
    });

    const query_summarize_url = "/api/query/" + query.id + "/summarize";

    $.ajax({
        type: "GET",
        url: query_summarize_url,
        dataType: "json",
        success: function (response) {
            if (response.status === false) {
                // sets a global variable so the alert is only shown once (otherwise queryInfo would also show the alert
                if (window.noResults === undefined) {
                    window.noResults = true;
                    alert('Query has no results. Build a new query');
                } else {
                    window.noResults = undefined;
                }
            }

            var networkInfoTable = document.getElementById('network-info-table');

            while (networkInfoTable.rows.length > 0) {
                networkInfoTable.deleteRow(0);
            }
            var row = 0;
            $.each(response.payload, function (key, value) {
                insertRow(networkInfoTable, row, key, value);
                row++
            });
        },
        error: function (request) {
            alert(query_summarize_url + ": " + request.message);
        }
    });
}

/**
 * Highlights border of nodes in nodeArray
 * @param {array} nodeArray
 */
function highlightNodeBorder(nodeArray) {

    var highlightNodes = d3.select("#graph-chart").selectAll(".node").filter(function (el) {
        return nodeArray.indexOf(el.id) >= 0;
    });

    if (highlightNodes["_groups"][0].length > 0) {
        $.each(highlightNodes["_groups"][0], function (index, value) {
            // Removes the fill - > black attribute
            value.children[1].setAttribute('fill', 'red');
            // Uses a different attribute rather than fill because fill it is modified when mouse over
            value.children[1].setAttribute('stroke', 'red');

        });
    }
}

/**
 * Remove border highlighting in all nodes
 */
function removeHighlightNodeBorder() {

    var highlightNodes = d3.select("#graph-chart").selectAll(".node");

    $.each(highlightNodes["_groups"][0], function (index, value) {
        // Set all nodes the default fill: black attribute
        value.children[1].removeAttribute('fill');
        value.children[1].removeAttribute('stroke');
    });

}

/**
 * Performs an AJAX call given an URL
 * @param {string} url
 * @param callback
 */
function doAjaxCallWithCallback(url, callback) {
    $.ajax({
        type: "GET",
        url: url,
        dataType: "json",
        success: callback,
        error: function (request) {
            alert(url + ": " + request.message);
        }
    });
}

function networkSizeChecking(data, tree) {
    if (data.nodes.length > maximumNodesToRender) { // Network bigger than 1500 nodes wont be rendered
        renderEmptyFrame();

        alert("The network you are trying to render contains: " + data.nodes.length + " nodes and " +
            data.links.length + " edges. To avoid crashing your browser, this network will only be rendered " +
            "after you give a more specific query or apply some filters with the right-hand tree navigator and" +
            "click in refresh network.")
    } else {
        initD3Force(data, tree);
    }
}

/**
 * Updates the network from a new query
 * @param {object} response: Response with the new Query ID
 * @param {InspireTree} tree: tree
 */
function updateQueryResponse(response, tree) {

    var positions = savePreviousPositions();

    window.query = response.id; // Updates in window the new query id

    reloadTree(tree); // Inits tree from network annotations

    const url = "/api/query/" + response.id + "/relabel";

    doAjaxCallWithCallback(url, function (networkResponse) {
        window.history.pushState("BiNE", "BiNE", "/explore/" + response.id); // Updates the URL

        var data = updateNodePosition(networkResponse, positions); // Loads new data, first empty all created divs and clear the current network

        clearUsedDivs(); // Cleans up used divs

        networkSizeChecking(data["jsonNetwork"], tree);

        highlightNodeBorder(data["newNodes"]); // Highlights nodes that were not in present query

        updateQueryTable(response.id); // Updates Query Table
    });
}


/**
 * Creates a new row in Node/Edge info table
 * @param {object} table: table object
 * @param {int} row: row number
 * @param {string} column1: string for column1
 * @param {string} column2: string for column2
 */
function insertRow(table, row, column1, column2) {

    var row = table.insertRow(row);
    var cell1 = row.insertCell(0);
    var cell2 = row.insertCell(1);
    cell1.innerHTML = column1;
    cell2.innerHTML = column2;
}


/**
 * Gets the query info from the API and renders it in a table\
 * @param {int} queryIdentifier
 */
function updateQueryTable(queryIdentifier) {
    doAjaxCallWithCallback("/api/query/" + queryIdentifier + "/info", displayQueryInfo);
}

/**
 * Expands the tree and enables search
 * @param {InspireTree} tree
 */
function initTreeTools(tree) {
    // Expands the tree
    tree.on("model.loaded", function () {
        tree.expand();
    });

    // Enables tree search
    $('#tree-search').on('keyup', function (ev) {
        tree.search(ev.target.value);
    });
}


/**
 * Updates tree childs and loads new query annotations
 * @param {InspireTree} tree
 */
function reloadTree(tree) {
    const url = "/api/query/" + window.query + "/tree/";

    doAjaxCallWithCallback(url, function (response) {
        if (response.status === false) {
            // sets a global variable so the alert is only shown once (otherwise queryInfo would also show the alert
            if (window.noResults === undefined) {
                window.noResults = true;
                alert('Query has no results. Build a new query');
            } else {
                window.noResults = undefined;
            }
        } else {
            tree.removeAll(); //Clean tree
            tree.load(response.payload);
            initTreeTools(tree);
        }
    });
}

/**
 * Updates network to a previous query
 * @param {object} response
 * @param {InspireTree} tree
 */
function backToOldQuery(response, tree) {
    if (response["parent"] === false) {
        alert("The current query has no parent");
    } else {
        updateQueryResponse(response, tree);
    }
}


$(document).ready(function () {

    // Export to BEL
    $("#bel-button").click(function () {
        $.ajax({
            url: "/api/query/" + window.query + "/export/bel",
            dataType: "text"
        }).done(function (response) {
            downloadText(response, "query-" + window.query + ".bel")
        });
    });

    // // Export network as an image
    d3.select("#save-svg-graph").on("click", function () {
        saveSvgAsPng(d3.select('#graph-svg').nodes()[0], "query-" + window.query + ".png");
    });

    updateQueryTable(window.query);  // Renders table info of the given query

    const url = "/api/query/" + window.query + "/tree/";

    doAjaxCallWithCallback(url, function (response) {
        // Inits the Annotation tree

        if (response.status === false) {
            // sets a global variable so the alert is only shown once (otherwise queryInfo would also show the alert
            if (window.noResults === undefined) {
                window.noResults = true;
                alert('Query has no results. Build a new query');
            } else {
                window.noResults = undefined;
            }
        } else {
            var tree = new InspireTree({
                target: "#tree",
                selection: {
                    mode: "checkbox",
                    multiple: true
                },
                data: response.payload
            });

            initTreeTools(tree); // Enable search/expands tree

            $.getJSON("/api/query/" + window.query + "/relabel", function (networkJson) {
                networkSizeChecking(networkJson, tree);
            });

            $("#refresh-network").on("click", function () {

                var treeSelection = getSelectedNodesFromTree(tree);

                if ($('#andortoggle').prop('checked') === true) {
                    treeSelection["and"] = true;
                }

                $.ajax({
                    url: "/api/query/" + window.query + "/add_annotation_filter/",
                    data: $.param(treeSelection, true),
                    dataType: "json"
                }).done(function (response) {
                    updateQueryResponse(response, tree);
                });
            });

            $("#collapse-tree").on("click", tree.collapseDeep);
        }

        // Back to parent query
        $("#parent-query").click(function () {
            const url = "/api/query/" + window.query + "/parent";
            doAjaxCallWithCallback(url, function (response) {
                backToOldQuery(response, tree);
            });
        });

        // Back to original query
        $("#original-query").click(function () {
            const url = "/api/query/" + window.query + "/ancestor";
            doAjaxCallWithCallback(url, function (response) {
                backToOldQuery(response, tree);
            });
        });
    });
});


/**
 * Renders empty frame
 */
function renderEmptyFrame() {
    // Render empty rectangle

    d = document;
    e = d.documentElement;
    g = d.getElementsByTagName("body")[0];

    var graphDiv = $("#graph-chart");
    var w = graphDiv.width(), h = graphDiv.height();

    var svg = d3.select("#graph-chart").append("svg")
        .attr("class", "svg-border")
        .attr("id", "graph-svg")
        .attr("width", w)
        .attr("height", h);

    // Background
    svg.append("rect")
        .attr("class", "background")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("fill", "#fcfbfb")
        .style("pointer-events", "all");


    // Text
    svg.append("text")
        .attr("class", "title")
        .attr("x", w / 3.2)
        .attr("y", h / 2)
        .text("Select your desired filters press refresh.");
}


/**
 * Clears used node/edge list and network
 * @example: Used to repopulate the html with a new network
 */
function clearUsedDivs() {
    $("#graph-chart").empty();
    $("#node-list").empty();
    $("#edge-list").empty();
}

///////////////////////////////////////
/// Functions for updating the graph //
///////////////////////////////////////


/**
 * Save previous positions of the nodes in the graph
 * @returns {object} Object with key to previous position
 */
function savePreviousPositions() {
    // Save current positions into prevLoc "object;
    var prevPos = {};

    // __data__ can be accessed also as an attribute (d.__data__)
    d3.selectAll(".node").data().map(function (d) {
        if (d) {
            prevPos[d.id] = [d.x, d.y];
        }

        return d;
    });

    return prevPos
}


/**
 * Update previous node position given new data (if nodes were previously there)
 * @param {object} jsonData: new node data
 * @param {object} prevPos object created by savePreviousPositions
 * @returns {object} update d3 JSON + array with new nodes
 */
function updateNodePosition(jsonData, prevPos) {

    var newNodesArray = [];

    // Set old locations back into the original nodes
    $.each(jsonData.nodes, function (index, value) {

        if (prevPos[value.id]) {

            oldX = prevPos[value.id][0];
            oldY = prevPos[value.id][1];
            // value.fx = oldX;
            // value.fy = oldY;
        } else {
            // If no previous coordinate... Start from off screen for a fun zoom-in effect
            oldX = -100;
            oldY = -100;
            newNodesArray.push(value.id);
        }

        value.x = oldX;
        value.y = oldY;

    });

    return {
        jsonNetwork: jsonData,
        newNodes: newNodesArray
    }
}


/**
 * Find duplicate ID nodes
 * @param {object} data
 * @returns {array} array of duplicates
 * @example: Necessary to node represent the nodes together with their function if they have the same cname
 */
function findDuplicates(data) {

    var hashMap = {};

    data.forEach(function (element, index) {

        if (!(element in hashMap)) {
            hashMap[element] = 0;
        }
        hashMap[element] += 1;
    });

    var duplicates = [];

    $.each(hashMap, function (key, value) {
        if (value > 1) {
            duplicates.push(key);
        }
    });

    return duplicates;
}

function downloadText(response, name) {
    var element = document.createElement("a");
    encoded_response = encodeURIComponent(response);
    element.setAttribute("href", "data:text/plain;charset=utf-8," + encoded_response);
    element.setAttribute("download", name);
    element.style.display = "none";
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
}

/**
 * Gets edge types as a dictionary
 * @param {object} edge json data
 * @return {object}
 */
function getEdgeTypes(edge) {
    var edgeTypes = {};

    $(edge.contexts).each(function (index, context) {
        edgeTypes[context.relation] = true;
    });

    return edgeTypes;
}

/**
 * Checks if there are any causal edges
 * @param {object} edge json data
 * @return {boolean}
 */
function doesEdgeHaveCausal(edge) {

    var edgeTypes = getEdgeTypes(edge);

    const causal_edge_types = ["decreases", "directlyDecreases", "increases", "directlyIncreases"];
    for (var i in causal_edge_types) {
        if (causal_edge_types[i] in edgeTypes) {
            return true;
        }
    }
    return false;
}


/**
 * Initialize d3 Force to plot network from json
 * @param {object} graph json data
 * @param {InspireTree} tree
 */
function initD3Force(graph, tree) {

    /**
     * Defines d3-context menu on right click
     */

    function updateQueryResponseTree(response) {
        updateQueryResponse(response, tree);
    }

    var nodeMenu = [
        {
            title: "Expand node neighbors from networks used in the query",
            action: function (elm, node, i) {
                // Variables explanation:
                // elm: [object SVGGElement] d: [object NodeObject] i: (#Number)
                $.ajax({
                    url: "/api/query/" + window.query + "/add_node_applier/expand_node_neighborhood_by_id/" + node.id,
                    dataType: "json"
                }).done(updateQueryResponseTree);
            },
            disabled: false // optional, defaults to false
        },
        {
            title: "Delete node",
            action: function (elm, node, i) {
                $.ajax({
                    url: "/api/query/" + window.query + "/add_node_applier/delete_node_by_id/" + node.id,
                    dataType: "json"
                }).done(updateQueryResponseTree);
            }
        },
        {
            title: "Create new query isolating this node",
            action: function (elm, node, i) {
                $.ajax({
                    url: "/api/query/" + window.query + "/isolated_node/" + node.id,
                    dataType: "json"
                }).done(updateQueryResponseTree);
            }
        }
    ];

    // Definition of context menu for nodes
    var edgeMenu = [
        {
            title: "Log evidences to console",
            action: function (elm, edge, i) {
                $.ajax({
                    url: "/api/edge/" + edge.id,
                    dataType: "json"
                }).done(function (response) {
                    console.log(response)
                });
            },
            disabled: false // optional, defaults to false
        }
    ];

    //////////////////////////////
    // Main graph visualization //
    //////////////////////////////

    // Enable nodes and edges tabs
    $(".disabled").attr("class", "nav-link ");

    // Force div
    var graphDiv = $("#graph-chart");
    // Node search div
    var nodePanel = $("#node-list");
    // Edge search div
    var edgePanel = $("#edge-list");

    clearUsedDivs();

    d = document;
    e = d.documentElement;
    g = d.getElementsByTagName("body")[0];

    var w = graphDiv.width(), h = graphDiv.height();

    // Highlight color variables

    // Size when zooming scale
    var size = d3.scalePow().exponent(1)
        .domain([1, 100])
        .range([8, 24]);

    // Simulation parameters
    var linkDistance = 100, fCharge = -1700, linkStrength = 0.7, collideStrength = 1;

    // Simulation defined with variables
    var simulation = d3.forceSimulation()
        .force("link", d3.forceLink()
            .distance(linkDistance)
            .strength(linkStrength)
        )
        .force("collide", d3.forceCollide()
            .radius(function (d) {
                return d.r + 10
            })
            .strength(collideStrength)
        )
        .force("charge", d3.forceManyBody()
            .strength(fCharge)
        )
        .force("center", d3.forceCenter(w / 2, h / 2))
        .force("y", d3.forceY(0))
        .force("x", d3.forceX(0));

    // Pin down functionality
    var nodeDrag = d3.drag()
        .on("start", dragStarted)
        .on("drag", dragged)
        .on("end", dragEnded);

    function dragStarted(d) {
        if (!d3.event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }

    function dragged(d) {
        d.fx = d3.event.x;
        d.fy = d3.event.y;
    }

    function dragEnded() {
        if (!d3.event.active) simulation.alphaTarget(0);
    }

    function releaseNode(d) {
        d.fx = null;
        d.fy = null;
    }

    //END Pin down functionality


    var svg = d3.select("#graph-chart").append("svg")
        .attr("class", "svg-border")
        .attr("id", "graph-svg")
        .attr("width", w)
        .attr("height", h);

    // // Create definition for arrowhead.
    svg.append("defs").append("marker")
        .attr("id", "arrowhead")
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 20)
        .attr("refY", 0)
        .attr("markerUnits", "strokeWidth")
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .attr("opacity", 0.3)
        .append("path")
        .attr("d", "M0,-5L10,0L0,5");

    // // Create definition for stub.
    svg.append("defs").append("marker")
        .attr("id", "stub")
        .attr("viewBox", "-1 -5 2 10")
        .attr("refX", 15)
        .attr("refY", 0)
        .attr("markerUnits", "strokeWidth")
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .attr("opacity", 0.3)
        .append("path")
        .attr("d", "M 0,0 m -1,-5 L 1,-5 L 1,5 L -1,5 Z");

    // // Create definition for cross.
    svg.append("defs").append("marker")
        .attr("id", "cross")
        .attr("viewBox", "-1 -5 2 10")
        .attr("refX", 15)
        .attr("refY", 0)
        .attr("markerUnits", "strokeWidth")
        .attr("markerWidth", 2)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .attr("opacity", 0.3)
        .append("path")
        .attr("d", "M 3,3 L 7,7 M 3,7 L 7,3");


    // Background
    svg.append("rect")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("fill", "#fcfbfb")
        .style("pointer-events", "all")
        // Zoom + panning functionality
        .call(d3.zoom()
            .scaleExtent([minZoom, maxZoom])
            .on("zoom", zoomed))
        .on("dblclick.zoom", null);


    function zoomed() {
        g.attr("transform", d3.event.transform);
    }

    var g = svg.append("g");  // g = svg object where the graph will be appended

    var linkedByIndex = {};
    graph.links.forEach(function (d) {
        linkedByIndex[d.source + "," + d.target] = true;
    });

    function isConnected(source, target) {
        return linkedByIndex[source.index + "," + target.index] || linkedByIndex[target.index + "," + source.index] || source.index === target.index;
    }

    function ticked() {
        link
            .attr("x1", function (d) {
                return d.source.x;
            })
            .attr("y1", function (d) {
                return d.source.y;
            })
            .attr("x2", function (d) {
                return d.target.x;
            })
            .attr("y2", function (d) {
                return d.target.y;
            });

        node
            .attr("transform", function (d) {
                return "translate(" + d.x + ", " + d.y + ")";
            });
    }


    simulation
        .nodes(graph.nodes)
        .on("tick", ticked);

    simulation.force("link")
        .links(graph.links);

    // Modify the simulation

    function inputted() {
        simulation.force("link").strength(+this.value);
        simulation.alpha(1).restart();
    }

    d3.select("#link-slider").on("input", inputted);

    // Definition of links nodes text...

    var link = g.selectAll(".link")
        .data(graph.links)
        .enter().append("line")
        .style("stroke-width", edgeStroke)
        .style("stroke-opacity", 0.4)
        .on("click", displayEdgeInfo)
        .on("contextmenu", d3.contextMenu(edgeMenu)) // Attach context menu to edge link
        .attr("class", function (edge) {
            if (doesEdgeHaveCausal(edge)) {
                return "link link_continuous";
            }

            edgeTypes = getEdgeTypes(edge);

            if ('negativeCorrelation' in edgeTypes) {
                return 'link link_dashed link_red';
            }

            if ('positiveCorrelation' in edgeTypes) {
                return 'link link_dashed link_blue';
            }

            return "link link_dashed"
        })
        .attr("marker-end", function (edge) {

            edgeTypes = getEdgeTypes(edge);

            if ("increases" in edgeTypes || "directlyIncreases" in edgeTypes) {
                return "url(#arrowhead)"
            } else if ("decreases" in edgeTypes || "directlyDecreases" in edgeTypes) {
                return "url(#stub)"
            } else {
                return ""
            }
        })
        .attr("marker-mid", function (edge) {

            edgeTypes = getEdgeTypes(edge);

            if ("causeNoChange" in edgeTypes) {
                return "url(#cross)"
            } else {
                return ""
            }
        });

    var node = g.selectAll(".nodes")
        .data(graph.nodes)
        .enter().append("g")
        .attr("class", "node")
        // Next two lines -> Pin down functionality
        .on("dblclick", releaseNode)
        // Box info
        .on("click", displayNodeInfo)
        // context-menu on right click
        .on("contextmenu", d3.contextMenu(nodeMenu)) // Attach context menu to node"s circle
        // Dragging
        .call(nodeDrag)
        .classed('new_node_highlight', function (data) {
            return 'pybel_highlight' in data;
        });

    var circle = node.append("circle")
        .attr("r", nominalBaseNodeSize)
        .attr("class", function (data) {
            return data.function
        });


    var text = node.append("text")
        .attr("class", "node-name")
        .attr("fill", "black")
        .attr("dx", 16)
        .attr("dy", ".35em")
        .text(getCanonicalName);

    // Highlight on mouse-enter and back to normal on mouseout
    node
        .on("mouseenter", function (data, index) {
            d3.select(this).classed('node_highlighted', true);


            link.classed("link_highlighted", function (o) {
                return o.source.index === index || o.target.index === index;
            });

            node.classed('node_highlighted', function (o) {
                return isConnected(data, o);
            });
        })
        .on("mousedown", function () {
            d3.event.stopPropagation();
        })
        .on("mouseout", function () {
            link.classed("link_highlighted", false);
            node.classed("node_highlighted", false);
        });


    // Highlight links on mouseenter and back to normal on mouseout
    link
        .on("mouseenter", function (data) {
            d3.select(this).classed('link_highlighted', true);
        })
        .on("mousedown", function () {
            d3.event.stopPropagation();
        })
        .on("mouseout", function () {
            d3.select(this).classed('link_highlighted', false);
        });

    /**
     * Freeze the graph when space is pressed
     */
    function freezeGraph() {
        if (d3.event.keyCode === 32) {
            simulation.stop();
        }
    }

    /**
     * Returns nodes that not pass the filter given a node array/property
     * @param {array} nodeArray
     * @param {string} property
     * @example: nodesNotInArray(['AKT1','APP'], 'cname')
     * @example: nodesNotInArray([1,2], 'id')
     */
    function nodesNotInArray(nodeArray, property) {
        return svg.selectAll(".node").filter(function (el) {
            return nodeArray.indexOf(el[property]) < 0;
        });
    }

    /**
     * Returns nodes that pass the filter given a node array/property
     * @param {array} nodeArray
     * @param {string} property
     * @example: nodesNotInArray(['AKT1','APP'], 'cname')
     * @example: nodesNotInArray([1,2], 'id')
     */
    function nodesInArray(nodeArray, property) {
        return svg.selectAll(".node").filter(function (el) {
            return nodeArray.indexOf(el[property]) >= 0;
        });
    }

    /**
     * Returns nodes that pass the filter given a node array/property (keeps the order of the nodeArray)
     * @param {array} nodeArray
     * @param {string} property
     * @example: nodesNotInArray(['AKT1','APP'], 'cname')
     * @example: nodesNotInArray([1,2], 'id')
     */
    function nodesInArrayKeepOrder(nodeArray, property) {
        return nodeArray.map(function (el) {
            var nodeObject = svg.selectAll(".node").filter(function (node) {
                return el === node[property]
            });
            return nodeObject._groups[0][0]
        });
    }

    /**
     * Resets default styles for nodes/edges/text on double click
     */
    function resetAttributesDoubleClick() {
        // On double click reset attributes (Important disabling the zoom behavior of dbl click because it interferes with this)
        svg.on("dblclick", function () {
            // Remove the overriding stroke so the links default back to the CSS definitions
            link.style("stroke", null);

            // SET default attributes //
            svg.selectAll(".link, .node").style("visibility", "visible")
                .style("opacity", "1");
            // Show node names
            svg.selectAll(".node-name").style("visibility", "visible").style("opacity", "1");
        });

    }

    /**
     * Resets default styles for nodes/edges/text
     */
    function resetAttributes() {
        // Reset visibility and opacity
        svg.selectAll(".link, .node").style("visibility", "visible").style("opacity", "1");
        // Show node names
        svg.selectAll(".node-name").style("visibility", "visible").style("opacity", "1");
        svg.selectAll(".node-name").style("display", "block");
    }

    /**
     * Hides the text of an array of Nodes
     * @param {array} nodeList
     * @param {boolean} visualization. If true: opacity to 0.1, false: 0.0 (hidden)
     * @example hideNodesText([1,34,5,56], false, 'id')
     */
    function hideNodesText(nodeList, visualization) {
        // Filter the text to those not belonging to the list of node names

        var nodesNotInList = g.selectAll(".node-name").filter(function (d) {
            return nodeList.indexOf(d.id) < 0;
        });

        if (visualization !== true) {
            //noinspection JSDuplicatedDeclaration
            var visualizationOption = "opacity", on = "1", off = "0.1";
        } else {
            //noinspection JSDuplicatedDeclaration
            var visualizationOption = "visibility", on = "visible", off = "hidden";
        }

        // Change display property to "none"
        $.each(nodesNotInList._groups[0], function (index, value) {
            value.style.setProperty(visualizationOption, off);
        });
    }

    /**
     * Hides the text of an array of node paths
     * @param {array} data
     * @param {boolean} visualization. If true: opacity to 0.1, false: 0.0 (hidden)
     * @param {string} property
     * @example hideNodesTextInPaths([[1,34,5,56],[123,234,3,4]], false, 'id')
     */
    function hideNodesTextInPaths(data, visualization, property) {
        // Array with all nodes in all paths
        var nodesInPaths = [];

        $.each(data, function (index, value) {
            $.each(value, function (index, value) {
                nodesInPaths.push(value);
            });
        });

        // Filter the text whose innerHTML is not belonging to the list of nodeIDs
        var textNotInPaths = g.selectAll(".node-name").filter(function (d) {
            return nodesInPaths.indexOf(d[property]) < 0;
        });

        if (visualization !== true) {
            //noinspection JSDuplicatedDeclaration
            var visualizationOption = "opacity", on = "1", off = "0.1";
        } else {
            //noinspection JSDuplicatedDeclaration
            var visualizationOption = "visibility", on = "visible", off = "hidden";
        }

        // Change display property to "none"
        $.each(textNotInPaths._groups[0], function (index, value) {
            value.style.setProperty(visualizationOption, off);
        });
    }

    /**
     * Changes the opacity to 0.1 of edges that are not in array
     * @param {array} edgeArray
     * @param {string} property of the edge to filter
     */
    function highlightEdges(edgeArray, property) {
        // Array with names of the nodes in the selected edge
        var nodesInEdges = [];

        // Filtered not selected links
        var edgesNotInArray = g.selectAll(".link").filter(function (edgeObject) {

            if (edgeArray.indexOf(edgeObject.source[property] + "-" + edgeObject.target[property]) >= 0) {
                nodesInEdges.push(edgeObject.source[property]);
                nodesInEdges.push(edgeObject.target[property]);
            } else return edgeObject;
        });

        var nodesNotInEdges = node.filter(function (nodeObject) {
            return nodesInEdges.indexOf(nodeObject[property]) < 0;
        });

        nodesNotInEdges.style("opacity", "0.1");
        edgesNotInArray.style("opacity", "0.1");

    }

    /**
     * Highlights nodes from array using property as filter and changes the opacity of the rest of nodes
     * @param {array} nodeArray
     * @param {string} property of the edge to filter
     */
    function highlightNodes(nodeArray, property) {
        // Filter not mapped nodes to change opacity
        var nodesNotInArray = svg.selectAll(".node").filter(function (el) {
            return nodeArray.indexOf(el[property]) < 0;
        });

        // Not mapped links
        var notMappedEdges = g.selectAll(".link").filter(function (el) {
            // Source and target should be present in the edge
            return !(nodeArray.indexOf(el.source[property]) >= 0 || nodeArray.indexOf(el.target[property]) >= 0);
        });

        nodesNotInArray.style("opacity", "0.1");
        notMappedEdges.style("opacity", "0.1");
    }


    /**
     * Highlights nodes which property is equal to condition
     * @param {string} property of the node that is going to checked
     * @param {string} condition property to be asserted
     */
    function highlightNodesByProperty(property, condition) {

        // Filter not mapped nodes to change opacity
        var nodesToHighlight = svg.selectAll(".node").filter(function (node) {
            return node[property] === condition;
        });

        // Set opacity of these nodes to 1
        $.each(nodesToHighlight._groups[0], function (index, node) {
            node.style.setProperty("opacity", "1");
        });
    }

    /**
     * Highlights edges which property is equal to condition
     * @param {string} relation relationship to filter
     */
    function highlightEdgesByRelationship(relation) {

        // Filter not mapped nodes to change opacity
        var edgeToHighlight = svg.selectAll(".link").filter(function (edge) {
            return relation in getEdgeTypes(edge)
        });

        // Set opacity of these edges to 1
        $.each(edgeToHighlight._groups[0], function (index, edge) {
            edge.style.setProperty("opacity", "1");
        });
    }

    /**
     * Colors an array of node paths
     * @param {array} data array of arrays
     * @param {boolean} visualization. If true: opacity to 0.1, false: 0.0 (hidden)
     * @example colorPaths([[1,34,5,56],[123,234,3,4]], false)
     */
    function colorPaths(data, visualization) {

        // data: nested array with all nodes in each path
        // visualization: parameter with visualization info ("hide" || "opaque)

        var link = g.selectAll(".link");

        ///////// Filter the nodes ////////

        // Array with all nodes in all paths
        var nodesInPaths = [];

        $.each(data, function (index, value) {
            $.each(value, function (index, value) {
                nodesInPaths.push(value);
            });
        });

        // Filtering the nodes that are not in any of the paths
        var nodesNotInPaths = svg.selectAll(".node").filter(function (el) {
            return nodesInPaths.indexOf(el.id) < 0;
        });

        if (visualization !== true) {
            //noinspection JSDuplicatedDeclaration
            var visualizationOption = "opacity", on = "1", off = "0.1";
        } else {
            //noinspection JSDuplicatedDeclaration
            var visualizationOption = "visibility", on = "visible", off = "hidden";
        }
        nodesNotInPaths.style(visualizationOption, off);

        ///////// Colour links in each path differently and hide others ////////

        // Colour the links ( Max 21 paths )
        var colorArray = ["#ff2200", " #282040", " #a68d7c", " #332b1a", " #435916", " #00add9", " #bfd0ff", " #f200c2",
            " #990014", " #d97b6c", " #ff8800", " #e5c339", " #5ba629", " #005947", " #005580", " #090040",
            " #8d36d9", " #e5005c", " #733941", " #993d00", " #80ffb2", " #66421a", " #e2f200", " #20f200", " #80fff6",
            " #002b40", " #6e698c", " #802079", " #330014", " #331400", " #ffc480", " #7ca682", " #264a4d", " #0074d9",
            " #220080", " #d9a3d5", " #f279aa"];

        // iter = number of paths ( Max 21 paths )
        if (data.length > colorArray.length) {
            //noinspection JSDuplicatedDeclaration
            var iter = colorArray.length;
        } else {
            //noinspection JSDuplicatedDeclaration
            var iter = data.length;
        }

        // First hide or set to opacity 0.1 all links
        link.style(visualizationOption, off);

        // Make visible again all the edges that are in any of the paths
        var edgesInPaths = [];

        for (var x = 0; x < iter; x++) {

            // Push the array (each path) to a new one where all paths are stored
            var path = link.filter(function (el) {
                // Source and target should be present in the edge and the distance in the array should be one
                return ((data[x].indexOf(el.source.id) >= 0 && data[x].indexOf(el.target.id) >= 0)
                    && (Math.abs(data[x].indexOf(el.source.id) - data[x].indexOf(el.target.id)) === 1));
            });

            edgesInPaths.push(path);
        }

        // Only the links that are in any of the paths are visible
        for (var j = 0, len = edgesInPaths.length; j < len; j++) {
            edgesInPaths[j].style(visualizationOption, on);
        }

        // For each path give a different color
        for (var i = 0; i < iter; i++) {
            var edgesInPath = link.filter(function (el) {
                // Source and target should be present in the edge and the distance in the array should be one
                return ((data[i].indexOf(el.source.id) >= 0 && data[i].indexOf(el.target.id) >= 0)
                    && (Math.abs(data[i].indexOf(el.source.id) - data[i].indexOf(el.target.id)) === 1));
            });

            // Select randomly a color and apply to this path
            edgesInPath.style("stroke", colorArray[getRandomInt(0, 21)]);
        }
    }

    /**
     * Process the response of shortest/all paths and highlight nodes/edges in them
     * @param {array} paths array containing path or paths
     * @param {boolean} checkbox boolean (hide other nodes if true)
     * @param {string} pathMethods if "all" -> all paths else-> shortests
     * @example colorPaths([[1,34,5,56],[123,234,3,4]], ,false)
     */
    function handlePathResponse(paths, checkbox, pathMethods) {
        if (pathMethods === "all") {
            if (paths.length === 0) {
                alert("No paths between the selected nodes");
            }

            resetAttributes();

            // Apply changes in style for select paths
            hideNodesTextInPaths(paths, checkbox, 'id');
            colorPaths(paths, checkbox);
            resetAttributesDoubleClick()
        } else {
            // Change style in force
            resetAttributes();

            var nodesNotInPath = nodesNotInArray(paths, 'id');

            var edgesNotInPath = g.selectAll(".link").filter(function (el) {
                // Source and target should be present in the edge and the distance in the array should be one
                return !((paths.indexOf(el.source.id) >= 0 && paths.indexOf(el.target.id) >= 0)
                    && (Math.abs(paths.indexOf(el.source.id) - paths.indexOf(el.target.id)) === 1));
            });

            // If checkbox is True -> Hide all, Else -> Opacity 0.1
            if (checkbox === true) {
                nodesNotInPath.style("visibility", "hidden");
                edgesNotInPath.style("visibility", "hidden");
            } else {
                nodesNotInPath.style("opacity", "0.1");
                edgesNotInPath.style("opacity", "0.05");
            }
            hideNodesText(paths, checkbox);
            resetAttributesDoubleClick();
        }
    }

    // Call freezeGraph when a key is pressed, freezeGraph checks whether this key is "Space" that triggers the freeze
    d3.select(window).on("keydown", freezeGraph);

    /////////////////////////////////////////////////////////////////////////
    // Build the node selection toggle and creates hashmap nodeNames to IDs /
    /////////////////////////////////////////////////////////////////////////

    // Build the node unordered list
    nodePanel.append("<ul id='node-list-ul' class='list-group checked-list-box not-rounded'></ul>");

    // Variable with all node names
    var nodeNames = [];

    // Create node list and create an array with duplicates
    $.each(graph.nodes, function (key, value) {
        nodeNames.push(getCanonicalName(value));

        $("#node-list-ul").append("<li class='list-group-item'><input class='node-checkbox' type='checkbox'>" +
            "<div class='circle " + value.function + "'>" +
            "</div><span class='node-" + value.id + "'>" + getCanonicalName(value) + "</span></li>");
    });

    var duplicates = findDuplicates(nodeNames);

    var nodeNamesToId = {};

    // Check over duplicate cnames and create hashmap to id
    $.each(graph.nodes, function (key, value) {
        // if the node has no duplicate show it in autocompletion with its cname

        var canonical_name = getCanonicalName(value);

        if (duplicates.indexOf(canonical_name < 0)) {
            nodeNamesToId[canonical_name] = value.id;
        } else {
            // if it has a duplicate show also the function after the cname
            nodeNamesToId[canonical_name + ' (' + value.function + ')'] = value.id;
        }
    });

    var checkNodes = $("#get-checked-nodes");

    checkNodes.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    // Highlight only selected nodes in the graph
    checkNodes.on("click", function (event) {
        event.preventDefault();
        var checkedItems = [];
        $(".node-checkbox:checked").each(function (idx, li) {
            // Get the class of the span element (node-ID) Strips "node-" and evaluate the string to integer
            checkedItems.push(li.parentElement.childNodes[2].className.replace("node-", ""));
        });

        resetAttributes();
        highlightNodes(checkedItems, 'id');
        resetAttributesDoubleClick();

    });

    ///////////////////////////////////////
    // Build the edge selection toggle
    ///////////////////////////////////////

    // Build the node unordered list
    edgePanel.append("<ul id='edge-list-ul' class='list-group checked-list-box not-rounded'></ul>");


    $.each(graph.links, function (key, edge) {

        edgeTypes = getEdgeTypes(edge);

        for (edgeType in edgeTypes) {
            $("#edge-list-ul").append("<li class='list-group-item'><input class='edge-checkbox' type='checkbox'><span id="
                + edge.source.id + '-' + edge.target.id + ">" + getCanonicalName(edge.source) + ' <strong><i>' + edgeType +
                '</i></strong> ' + getCanonicalName(edge.target) + "</span></li>");
        }
    });

    var checkNodesButton = $("#get-checked-edges");

    checkNodesButton.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    checkNodesButton.on("click", function (event) {
        event.preventDefault();

        var checkedItems = [];
        $(".edge-checkbox:checked").each(function (idx, li) {
            checkedItems.push(li.parentElement.childNodes[1].id);
        });

        resetAttributes();

        highlightEdges(checkedItems, 'id');

        resetAttributesDoubleClick()
    });

    var highlightButton = $("#highlight-button");
    highlightButton.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    // Highlight stuffs
    highlightButton.click(function (event) {
        event.preventDefault();

        // Reduce opacity of all nodes/edges to minimum
        svg.selectAll(".node").style("opacity", "0.1");
        svg.selectAll(".link").style("opacity", "0.1");

        $(".highlight-checkbox:checked").each(function (idx, li) {
            var highlightSpan = li.parentElement.parentElement.childNodes[3];

            var spanClass = highlightSpan.className.split("-");

            // If "node" is the first element of the class, call highlight by nodes. Else highlight by edge
            if (spanClass[0] === "node") {
                highlightNodesByProperty(spanClass[1], highlightSpan.id);
            } else {
                highlightEdgesByRelationship(highlightSpan.id);
            }
        });

        resetAttributesDoubleClick()

    });

    //// Path stuffs ////

    var pathForm = $("#path-form");

    var pathButton = $("#button-paths");

    pathButton.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    pathButton.on("click", function () {
        if (pathForm.valid()) {

            var checkbox = pathForm.find("input[name='visualization-options']").is(":checked");

            args = {};

            args["paths_method"] = $("input[name=paths_method]:checked", pathForm).val();

            var undirected = pathForm.find("input[name='undirectionalize']").is(":checked");

            if (undirected) {
                args["undirected"] = undirected;
            }

            const query_paths_url = "/api/query/" + window.query + "/paths/" +
                nodeNamesToId[pathForm.find("input[name='source']").val()] + "/" +
                nodeNamesToId[pathForm.find("input[name='target']").val()] + "/";

            $.ajax({
                url: query_paths_url,
                type: pathForm.attr("method"),
                dataType: "json",
                data: $.param(args, true),
                success: function (paths) {
                    handlePathResponse(paths, checkbox, args["paths_method"]);
                },
                error: function (request) {
                    alert(query_paths_url + ': ' + request.responseText);
                }
            })
        }
    });

    // Path validation form
    pathForm.validate({
        rules: {
            source: {
                required: true,
                minlength: 2
            },
            target: {
                required: true,
                minlength: 2
            }
        },
        messages: {
            source: "Please enter a valid source",
            target: "Please enter a valid target"
        }
    });

    /// Random Paths ////

    var randomPaths = $("#random-paths");

    randomPaths.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    randomPaths.on("click", function () {
            $.ajax({
                url: "/api/query/" + window.query + "/paths/random",
                dataType: "json",
                success: function (paths) {
                    handlePathResponse(paths, false, null);
                },
                error: function (request) {
                    alert(request.responseText);
                }
            })
        }
    );

    // Path autocompletion input
    var nodeNamesSorted = Object.keys(nodeNamesToId).sort();

    $("#source-node").autocomplete({
        source: nodeNamesSorted,
        appendTo: "#paths"
    });

    $("#target-node").autocomplete({
        source: nodeNamesSorted,
        appendTo: "#paths"
    });

    // Update Node Dropdown
    $("#node-search").on("keyup", function () {
        // Get value from search form (fixing spaces and case insensitive
        var searchText = $(this).val();
        searchText = searchText.toLowerCase();
        searchText = searchText.replace(/\s+/g, "");

        $.each($("#node-list-ul")[0].childNodes, updateNodeArray);

        function updateNodeArray() {
            var currentLiText = $(this).find("span")[0].innerHTML,
                showCurrentLi = ((currentLiText.toLowerCase()).replace(/\s+/g, "")).indexOf(searchText) !== -1;
            $(this).toggle(showCurrentLi);
        }
    });

    // Update Edge Dropdown
    $("#edge-search").on("keyup", function () {
        // Get value from search form (fixing spaces and case insensitive
        var searchText = $(this).val();
        searchText = searchText.toLowerCase();
        searchText = searchText.replace(/\s+/g, "");

        $.each($("#edge-list-ul")[0].childNodes, updateEdgeArray);

        function updateEdgeArray() {

            var currentLiText = $(this).find("span")[0].innerHTML,
                showCurrentLi = ((currentLiText.toLowerCase()).replace(/\s+/g, "")).indexOf(searchText) !== -1;
            $(this).toggle(showCurrentLi);
        }
    });


    // Update Highlight Dropdown
    $("#highlight-search").on("keyup", function () {
        // Get value from search form (fixing spaces and case insensitive
        var searchText = $(this).val();
        searchText = searchText.toLowerCase();
        searchText = searchText.replace(/\s+/g, "");

        $.each($("#highlight-list-ul")[0].childNodes, updateEdgeArray);

        function updateEdgeArray() {

            if ($(this)[0].nodeName !== "#text") {
                var currentLiText = $(this).find("span")[0].innerHTML,
                    showCurrentLi = ((currentLiText.toLowerCase()).replace(/\s+/g, "")).indexOf(searchText) !== -1;
                $(this).toggle(showCurrentLi);
            }
        }
    });

    // Get or show all paths between two nodes via Ajax

    var betwennessForm = $("#betweenness-centrality");

    var betweennessButton = $("#betweenness-button");

    betweennessButton.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    betweennessButton.on("click", function () {
        if (betwennessForm.valid()) {
            $.ajax({
                url: "/api/query/" + window.query + "/centrality/" + betwennessForm.find("input[name='betweenness']").val(),
                type: betwennessForm.attr("method"),
                dataType: "json",
                success: function (data) {

                    var nodesToIncrease = nodesInArrayKeepOrder(data, 'id');

                    var nodesToReduce = nodesNotInArray(data, 'id');

                    // Reduce to 7 radius the nodes not in top x
                    $.each(nodesToReduce._groups[0], function (index, value) {
                        value.childNodes[0].setAttribute("r", "7");
                    });

                    // Make bigger by factor scale the nodes in the top x
                    var nodeFactor = (nominalBaseNodeSize / 3) / nodesToIncrease.length;
                    var factor = nominalBaseNodeSize + nodeFactor;

                    $.each(nodesToIncrease.reverse(), function (index, value) {
                        value.childNodes[0].setAttribute("r", factor);
                        factor += nodeFactor;
                    });
                },
                error: function (request) {
                    alert(request.responseText);
                }
            })
        }
    });

    betwennessForm.validate({
        rules: {
            betweenness: {
                required: true,
                digits: true
            }
        },
        messages: {
            betweenness: "Please enter a number"
        }
    });


    // Get normalized results from NPA analysis given an experiment ID

    var heatDiffusionForm = $("#heat-diffusion-form");

    var heatDiffusionButton = $("#heat-diffusion-button");

    heatDiffusionButton.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    heatDiffusionButton.on("click", function () {
        if (heatDiffusionForm.valid()) {
            var experimentID = $("#analysis_id").val();

            $.ajax({
                url: "/api/query/" + window.query + "/analysis/" + experimentID + "/median",
                type: heatDiffusionForm.attr("method"),
                dataType: "json",
                success: function (data) {

                    var distribution = Object.values(data).filter(Number);

                    var midRange = (Math.max.apply(Math, distribution) + Math.min.apply(Math, distribution)) / 2;

                    var normalizedData = {};

                    $.each(data, function (key, value) {
                        // In case value is null
                        if (value) {
                            normalizedData[key] = value - Math.abs(midRange);
                        }
                    });
                    // Keys are stored as strings need conversation to JS numbers
                    var nodeIDStrings = Object.keys(normalizedData);
                    var mappedNodes = nodesInArrayKeepOrder(nodeIDStrings, 'id');
                    $.each(mappedNodes, function (index, value) {
                        // Order is maintain so it uses the index to get iterate over normalizedData applying (constant/midrange)
                        value.childNodes[0].setAttribute("r", Math.abs(normalizedData[nodeIDStrings[index]] * (5 / midRange)));
                    });
                },
                error: function (request) {
                    alert(request.responseText);
                }
            })
        }
    });

    heatDiffusionForm.validate({
        rules: {
            analysis_id: {
                required: true,
                digits: true
            }
        },
        messages: {
            analysis_id: "Please enter a number corresponding to the ID of an experiment"
        }
    });

    ///////////////////////
    // Tool modal buttons /
    ///////////////////////

    var toolButtonClass = $(".explorer-tool");

    toolButtonClass.off("click");

    toolButtonClass.on("click", function () {
        $.ajax({
            url: "/api/query/" + window.query + "/add_applier/" + $(this).data('value'),
            dataType: "json"
        }).done(function (response) {
            updateQueryResponse(response, tree);
        });
    });

    ///////////////////////
    // Tool modal buttons /
    ///////////////////////

    // Hide node names button

    var hideNodeNames = $("#hide-node-names");

    hideNodeNames.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    // Hide text in graph
    hideNodeNames.on("click", function () {
        svg.selectAll(".node-name").style("display", "none");
    });

    var restoreNodeNames = $("#restore-node-names");

    restoreNodeNames.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    // Hide text in graph
    restoreNodeNames.on("click", function () {
        svg.selectAll(".node-name").style("display", "block");
    });

    var restoreAll = $("#restore");

    restoreAll.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    // Restore all
    restoreAll.on("click", function () {
        resetAttributes();
    });

    var removeNodeHighlighting = $("#remove-node-highlighting");

    removeNodeHighlighting.off("click"); // It will unbind the previous click if multiple graphs has been rendered

    // Restore all
    removeNodeHighlighting.on("click", function () {
        removeHighlightNodeBorder();
    });


    // Edge feedback
    const voteUpButton = $('#edge-feedback-vote-up')
        .on('click', function () {
            $.ajax({
                url: "/api/edge/" + $(this).data('edge') + "/vote/up",
                dataType: "json",
                success: function (buttonResponse) {
                    $(this).removeClass('btn-default').addClass('btn-success');
                }
            });
        });

    const voteDownButton = $('#edge-feedback-vote-down')
        .on('click', function () {
            $.ajax({
                url: "/api/edge/" + $(this).data('edge') + "/vote/down",
                dataType: "json",
                success: function (buttonResponse) {
                    $(this).removeClass('btn-default').addClass('btn-warning');
                }
            });
        });

    const commentTextBox = $('#comment-text');

    const commentButton = $('#comment-button')
        .on('click', function () {
            var commentText = commentTextBox.val();

            $.ajax({
                url: "/api/edge/" + $(this).data('edge') + "/comment",
                data: {
                    'comment': commentText
                },
                dataType: "json",
                success: function (buttonResponse) {
                    commentList.append('<div class="list-group-item"><h4 class="list-group-item-heading">Me</h4><p class="list-group-item-text">' + commentText + "</p></div>");
                    commentTextBox.val("");
                }
            });
        });

    const commentList = $('#edge-feedback-comments-list');

    const edgeFeedbackModal = $('#edge-feedback')
        .on('show.bs.modal', function (event) {
            var button = $(event.relatedTarget); // Button that triggered the modal
            var edge_id = button.data('edge'); // Extract info from data-* attributes
            // If necessary, you could initiate an AJAX request here (and then do the updating in a callback).
            // Update the modal's content. We'll use jQuery here, but you could use a data binding library or other methods instead.

            voteUpButton.data('edge', edge_id);
            voteDownButton.data('edge', edge_id);
            commentButton.data('edge', edge_id);

            var modal = $(this);
            modal.find('.modal-title').text('Edge ' + edge_id.slice(0, 10));

            $.ajax({
                url: "/api/edge/" + edge_id,
                dataType: "json",
                success: function (response) {
                    vote = response.vote;

                    if (vote === 1) {
                        voteUpButton.removeClass('btn-default').addClass('btn-success');
                    } else if (vote === -1) {
                        voteDownButton.removeClass('btn-default').addClass('btn-danger');
                    }

                    commentList.empty();
                    $.each(response.comments, function (index, val) {
                        commentList.append('<div class="list-group-item"><h4 class="list-group-item-heading">' + val.user.email + '</h4><p class="list-group-item-text">' + val.comment + "</p></div>");
                    });
                },
                error: function (request) {
                    alert(request.message);
                }
            });
        })
        .on('hide.bs.modal', function (event) {
            voteUpButton.removeClass('btn-success').addClass('btn-default');
            voteDownButton.removeClass('btn-danger').addClass('btn-default');
            commentTextBox.val('');
        });


    $(".explorer-download").click(function () {
        window.location.href = '/api/query/' + window.query + '/export/' + $(this).data('format');
    });

    $('#analysis-upload-button').click(function () {
        window.location.href = '/experiment/from_query/' + window.query + '/upload';
    })
}
