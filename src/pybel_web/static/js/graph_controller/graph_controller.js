/**
 * This JS file controls and connect the network to the PyBEL-web API.
 *
 * @summary   Network controller of PyBEL-web explorer
 *
 * @requires jquery, d3, d3-context-menu, inspire-tree, blob
 *
 */


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

/**
 * Renders node info table
 * @param {object} node object
 */
function displayNodeInfo(node) {

    var dynamicTable = document.getElementById('info-table');

    while (dynamicTable.rows.length > 0) {
        dynamicTable.deleteRow(0);
    }

    var nodeObject = {};

    if (node.cname) {
        nodeObject["Node"] = node.cname + " (ID: " + node.id + ")";
    }
    if (node.name) {
        nodeObject["Name"] = node.cname;
    }
    if (node.function) {
        nodeObject["Function"] = node.function;
    }
    if (node.namespace) {
        nodeObject["Namespace"] = node.namespace;
    }
    if (node.label) {
        nodeObject["Label"] = node.label
    }
    if (node.description) {
        nodeObject["Description"] = node.description
    }

    var row = 0;
    $.each(nodeObject, function (key, value) {
        insertRow(dynamicTable, row, key, value);
        row++
    });
}

/**
 * Renders edge info table
 * @param {object} edge object
 */
function displayEdgeInfo(edge) {

    var edgeObject = {};

    var dynamicTable = document.getElementById('info-table');

    while (dynamicTable.rows.length > 0) {
        dynamicTable.deleteRow(0);
    }

    // Check if object property exists

    if (edge.evidence) {
        edgeObject["Evidence"] = edge.evidence;
    }
    if (edge.citation) {
        edgeObject["Citation"] = "<a href=https://www.ncbi.nlm.nih.gov/pubmed/" + edge.citation.reference + " target='_blank' " +
            "style='color: blue; text-decoration: underline'>" + edge.citation.reference + "</a>";
    }
    if (edge.relation) {
        edgeObject["Relationship"] = edge.relation;
    }
    if (edge.annotations) {
        edgeObject["Annotations"] = JSON.stringify(edge.annotations);
    }
    if (edge.source.cname) {
        edgeObject["Source"] = edge.source.cname + " (ID: " + edge.source.id + ")";
    }
    if (edge.target.cname) {
        edgeObject["Target"] = edge.target.cname + " (ID: " + edge.target.id + ")";
    }

    var row = 0;
    $.each(edgeObject, function (key, value) {
        insertRow(dynamicTable, row, key, value);
        row++
    });
}

/**
 * Renders query info table
 * @param {object} query object
 */
function displayQueryInfo(query) {

    var dynamicTable = document.getElementById('query-table');

    var queryObject = {};

    queryObject["Query ID"] = query.id;

    queryObject["Assembly (Networks IDs)"] = query.network_ids;

    if (query.seeding !== "[]") {
        var querySeeding = query.seeding.map(function (object) {
            if (object.type == "annotation") {

                var arr = [];

                for (var key in object.data) {
                    if (object.data.hasOwnProperty(key)) {
                        arr.push(key + '=' + object.data[key]);
                    }
                }
                return object.type + ": [" + arr.join(',') + "]";
            }
            return object.type + ": [" + object.data + "]";
        });
        queryObject["Seeding"] = querySeeding;
    }

    if (query.pipeline !== "[]") {
        var queryPipeline = query.pipeline.map(function (object) {
            return object.function;
        });

        queryObject["Pipeline"] = queryPipeline.join(", ");

    }

    var row = 0;
    $.each(queryObject, function (key, value) {
        insertRow(dynamicTable, row, key, value);
        row++
    });
}

/**
 * Highlights nodes in nodeArray
 * @param {array} nodeArray
 */
function highlightNodeBorder(nodeArray) {

    var highlightNodes = d3.select("#graph-chart").selectAll(".node").filter(function (el) {
        return nodeArray.indexOf(el.id) >= 0;
    });

    if (highlightNodes["_groups"][0].length > 0) {
        $.each(highlightNodes["_groups"][0], function (index, value) {
            value.children[1].setAttribute('style', 'stroke: red');
        });
    }
}

/**
 * Remove highlighting all nodes
 */
// TODO: Fix this
function removeHighlightNodeBorder() {

    var highlightNodes = d3.select("#graph-chart").selectAll(".node");

    $.each(highlightNodes["_groups"][0], function (index, value) {
        value.children[1].setAttribute('style', 'stroke: black');
    });

}

/**
 * Automatically select nodes in the tree given an URL
 * @param {InspireTree} tree
 * @param {string} url
 * @param {array} blackList parameters in the URL not belonging to the tree
 */
function selectNodesInTreeFromURL(tree, url, blackList) {
    // Select in the tree the tree-nodes in the URL
    var selectedNodes = {};

    $.each(url, function (index, value) {
        if (!(index in blackList)) {
            if (Array.isArray(value)) {
                $.each(value, function (childIndex, child) {
                    if (index in selectedNodes) {
                        selectedNodes[index].push(child.replace(/\+/g, " "));
                    }
                    else {
                        selectedNodes[index] = [child.replace(/\+/g, " ")];
                    }
                });
            }
            else {
                if (index in selectedNodes) {
                    selectedNodes[index].push(value.replace(/\+/g, " "));
                }
                else {
                    selectedNodes[index] = [value.replace(/\+/g, " ")];
                }
            }
        }
    });

    var treeNodes = tree.nodes();

    $.each(treeNodes, function (index, value) {
        if (value.text in selectedNodes) {
            $.each(value.children, function (child, childValue) {

                if (selectedNodes[value.text].indexOf(childValue.text) >= 0) {
                    childValue.check();
                }
            });
        }
    });
}


/**
 * Renders the network given default parameters
 * @param {InspireTree} tree
 */
function renderNetworkFirstTime(tree) {

    $.getJSON("/api/network/" + window.query, function (data) {
        if (data.nodes.length > 1000) {// Network bigger than 1000 nodes wont be render
            renderEmptyFrame();

            alert("The network you are trying to render contains: " + data.nodes.length + " nodes and " +
                data.links.length + " edges. To avoid crashing your browser, this network will only be rendered " +
                "after you click in refresh network.Please consider giving a more specific query or applying some " +
                "filters using the right-hand tree navigator.")
        }

        else {
            initD3Force(data, tree);
        }
    });

    window.history.pushState("BiNE", "BiNE", "/explore/query/" + window.query);
}


/**
 * Performs an AJAX call given an URL
 * @param {string} url
 */
function doAjaxCall(url) {

    var result = null;
    $.ajax({
        type: "GET",
        url: url,
        dataType: "json",
        success: function (data) {
            result = data;
        }, error: function (request) {
            alert(request.message);
        },
        data: {},
        async: false
    });

    return result
}


function updateQueryResponse(response, tree) {
    var positions = savePreviousPositions();

    window.query = response.id;

    var networkResponse = doAjaxCall("/api/network/" + window.query);

    window.history.pushState("BiNE", "BiNE", "/explore/query/" + window.query);

    // Load new data, first empty all created divs and clear the current network
    var data = updateNodePosition(networkResponse, positions);

    clearUsedDivs();

    if (data["json"].length > 1000) {// Network bigger than 1000 nodes wont be render
        renderEmptyFrame();

        alert("The network you are trying to render contains: " + data.nodes.length + " nodes and " +
            data.links.length + " edges. To avoid crashing your browser, this network will only be rendered " +
            "after you click in refresh network.Please consider giving a more specific query or applying some " +
            "filters using the right-hand tree navigator.")
    }

    else {
        initD3Force(data["json"], tree);

        highlightNodeBorder(data["newNodes"]);
    }

}


/**
 * Creates a new row in Node/Edge info table
 */
function insertRow(table, row, column1, column2) {

    var row = table.insertRow(row);
    var cell1 = row.insertCell(0);
    var cell2 = row.insertCell(1);
    cell1.innerHTML = column1;
    cell2.innerHTML = column2;
}


/**
 * Gets the info from query and renders its table
 */
function updateQueryTable() {
    var queryInfo = doAjaxCall("/api/query/" + window.query + "/info");

    displayQueryInfo(queryInfo);
}


/**
 * Renders tree for annotation filtering
 */
function initTree() {

    // Initiate the tree and expands it with the annotations in the query
    var tree = new InspireTree({
        target: "#tree",
        selection: {
            mode: "checkbox",
            multiple: true
        },
        data: doAjaxCall("/api/network/query/" + window.query + "/tree/")
    });

    tree.on("model.loaded", function () {
        tree.expand();
    });

    // Enables tree search
    $('#tree-search').on('keyup', function (ev) {
        tree.search(ev.target.value);
    });

    return tree
}


$(document).ready(function () {

    updateQueryTable();

    tree = initTree();

    renderNetworkFirstTime(tree);

    $("#refresh-network").on("click", function () {

        var treeSelection = getSelectedNodesFromTree(tree);

        if ($('#andortoggle').prop('checked') === true) {
            treeSelection["and"] = true;
        }

        $.ajax({
            url: "/api/query/" + window.query + "/add_annotation_filter/?" + $.param(treeSelection, true),
            dataType: "json"
        }).done(function (response) {
            updateQueryResponse(response, initTree())
        });
    });

    $("#collapse-tree").on("click", function () {
        tree.collapseDeep();
    });

    // Export network as an image
    d3.select("#save-svg-graph").on("click", downloadSvg);

    // Export to BEL
    $("#bel-button").click(function () {
        $.ajax({
            url: "/api/network/" + window.query + "/export/bel",
            dataType: "text"
        }).done(function (response) {
            downloadText(response, "MyNetwork.bel")
        });
    });

    // Export to GraphML
    $("#graphml-button").click(function () {
        window.location.href = "/api/network/" + window.query + "/export/graphml";
    });

    // Export to bytes
    $("#bytes-button").click(function () {
        window.location.href = "/api/network/" + window.query + "/export/bytes";

    });

    // Export to CX
    $("#cx-button").click(function () {
        window.location.href = "/api/network/" + window.query + "/export/cx";
    });

    // Export to CSV
    $("#csv-button").click(function () {
        window.location.href = "/api/network/" + window.query + "/export/csv";
    });

    $("#nodelink-button").click(function () {
        window.location.href = "/api/network/" + window.query + "/export/json";
    });

    // Back to parent query
    $("#parent-query").click(function () {
        var response = doAjaxCall("/api/query/" + window.query + "/parent");
        if (response["parent"] === false) {
            alert("The current query has no parent");
        }
        else {
            updateQueryResponse(response, initTree())
        }
    });

    // Back to original query
    $("#original-query").click(function () {
        var response = doAjaxCall("/api/query/" + window.query + "/parent")
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
        json: jsonData,
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


function downloadSvg() {
    try {
        var isFileSaverSupported = !!new Blob();
    } catch (e) {
        alert("blob not supported");
    }

    var html = d3.select("svg")
        .attr("title", "test2")
        .attr("version", 1.1)
        .attr("xmlns", "http://www.w3.org/2000/svg")
        .node().parentNode.innerHTML;

    var blob = new Blob([html], {type: "image/svg+xml"});
    saveAs(blob, "MyGraph.svg");
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
 * Initialize d3 Force to plot network from json
 * @param {object} graph json data
 * @param {InspireTree} tree
 */
function initD3Force(graph, tree) {

    /**
     * Defines d3-context menu on right click
     */

    var nodeMenu = [
        {
            title: "Expand node neighbors from networks used in the query",
            action: function (elm, node, i) {
                // Variables explanation:
                // elm: [object SVGGElement] d: [object NodeObject] i: (#Number)
                $.ajax({
                    url: "/api/query/" + window.query + "/add_node_applier/expand_node_neighborhood_by_id/" + node.id,
                    dataType: "json"
                }).done(function (response) {
                    updateQueryResponse(response, tree)
                });
            },
            disabled: false // optional, defaults to false
        },
        {
            title: "Expand node neighbors from user universe",
            action: function (elm, node, i) {
                // Variables explanation:
                // elm: [object SVGGElement] d: [object NodeObject] i: (#Number)
                $.ajax({
                    url: "/api/network/", //TODO
                    dataType: "json"
                }).done(function (response) {
                    updateQueryResponse(response, tree)
                });
            },
            disabled: false // optional, defaults to false
        },
        {
            title: "Delete node",
            action: function (elm, node, i) {
                $.ajax({
                    url: "/api/query/" + window.query + "/add_node_applier/delete_node_by_id/" + node.id,
                    dataType: "json"
                }).done(function (response) {
                    updateQueryResponse(response, tree)
                });
            }
        }
    ];

    // Definition of context menu for nodes
    var edgeMenu = [
        {
            title: "Log evidences to console",
            action: function (elm, link, i) {

                console.log(link.source);
                console.log(link.target);

                $.ajax({
                    url: "/api/edges/provenance/" + link.source.id + "/" + link.target.id,
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

    var focusNode = null, highlightNode = null;

    // Highlight color variables

    var highlightNodeBoundering = "#4EB2D4"; // Highlight color of the node boundering

    var highlightedLinkColor = "#4EB2D4"; // Highlight color of the edge

    var highlightText = "#4EB2D4"; // Text highlight color

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

    var circleColor = "black";
    var defaultLinkColor = "#888";

    const nominalBaseNodeSize = 10; // Default node radius

    var nominalStroke = 2.5;  // Edge width
    var minZoom = 0.1, maxZoom = 10; // Zoom variables

    var svg = d3.select("#graph-chart").append("svg")
        .attr("class", "svg-border")
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
        .append("path")
        .attr("d", "M 0,0 m -1,-5 L 1,-5 L 1,5 L -1,5 Z");

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

    function isConnected(a, b) {
        return linkedByIndex[a.index + "," + b.index] || linkedByIndex[b.index + "," + a.index] || a.index === b.index;
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

    // Definition of links nodes text...

    var link = g.selectAll(".link")
        .data(graph.links)
        .enter().append("line")
        .style("stroke", function (d) {
            if ('pybel_highlight' in d) {
                return d['pybel_highlight']
            }
            else {
                return defaultLinkColor
            }
        })
        .style("stroke-width", nominalStroke)
        .on("click", function (d) {
            displayEdgeInfo(d);
        })
        .on("contextmenu", d3.contextMenu(edgeMenu)) // Attach context menu to edge link
        .attr("class", function (d) {
            if (["decreases", "directlyDecreases", "increases", "directlyIncreases", "negativeCorrelation",
                    "positiveCorrelation"].indexOf(d.relation) >= 0) {
                return "link link_continuous"
            }
            else {
                return "link link_dashed"
            }
        })
        .attr("marker-start", function (d) {
            if ("positiveCorrelation" === d.relation) {
                return "url(#arrowhead)"
            }
            else if ("negativeCorrelation" === d.relation) {
                return "url(#stub)"
            }
            else {
                return ""
            }
        })
        .attr("marker-end", function (d) {
            if (["increases", "directlyIncreases", "positiveCorrelation"].indexOf(d.relation) >= 0) {
                return "url(#arrowhead)"
            }
            else if (["decreases", "directlyDecreases", "negativeCorrelation"].indexOf(d.relation) >= 0) {
                return "url(#stub)"
            }
            else {
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
        .on("click", function (d) {
            displayNodeInfo(d);
        })
        // context-menu on right click
        .on("contextmenu", d3.contextMenu(nodeMenu)) // Attach context menu to node"s circle
        // Dragging
        .call(nodeDrag);

    var circle = node.append("circle")
        .attr("r", nominalBaseNodeSize)
        .attr("class", function (d) {
            return d.function
        })
        .style("stroke-width", nominalStroke)
        .style("stroke", function (d) {
            if ('pybel_highlight' in d) {
                return d['pybel_highlight']
            } else {
                return circleColor
            }
        });

    var text = node.append("text")
        .attr("class", "node-name")
        // .attr("id", nodehashes[d])
        .attr("fill", "black")
        .attr("dx", 16)
        .attr("dy", ".35em")
        .text(function (d) {
            return d.cname
        });

    // Highlight on mouseenter and back to normal on mouseout
    node.on("mouseenter", function (d) {
        setHighlight(d);
    })
        .on("mousedown", function () {
            d3.event.stopPropagation();
        }).on("mouseout", function () {
        exitHighlight();
    });

    function exitHighlight() {
        highlightNode = null;
        if (focusNode === null) {
            if (highlightNodeBoundering !== circleColor) {
                circle.style("stroke", function (d) {
                    if ("pybel_highlight" in d) {
                        return d["pybel_highlight"]
                    }
                    else {
                        return circleColor
                    }
                });
                text.style("fill", "black");
                link.style("stroke", function (d) {
                    if ("pybel_highlight" in d) {
                        return d["pybel_highlight"]
                    }
                    else {
                        return defaultLinkColor
                    }
                })

            }
        }
    }

    function setHighlight(d) {
        if (focusNode !== null) d = focusNode;
        highlightNode = d;

        if (highlightNodeBoundering !== circleColor) {
            circle.style("stroke", function (o) {
                return isConnected(d, o) ? highlightNodeBoundering : circleColor;
            });
            text.style("fill", function (o) {
                return isConnected(d, o) ? highlightText : "black";
            });
            link.style("stroke", function (o) {
                // All links connected to the node you hover on
                return o.source.index === d.index || o.target.index === d.index ? highlightedLinkColor : defaultLinkColor;
            });
        }
    }

    // Highlight links on mouseenter and back to normal on mouseout
    link.on("mouseenter", function (d) {
        link.style("stroke", function (o) {
            // Specifically the link you hover on
            return o.source.index === d.source.index && o.target.index === d.target.index ? highlightedLinkColor : defaultLinkColor;
        });
    })
        .on("mousedown", function () {
            d3.event.stopPropagation();
        }).on("mouseout", function () {
        link.style("stroke", defaultLinkColor);
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
     */    function nodesNotInArray(nodeArray, property) {
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
            // SET default color
            svg.selectAll(".link").style("stroke", defaultLinkColor);
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
     * @param {string} property
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

            if (edgeArray.indexOf(edgeObject.source[property] + " " + edgeObject.relation + " " + edgeObject.target[property]) >= 0) {
                nodesInEdges.push(edgeObject.source[property]);
                nodesInEdges.push(edgeObject.target[property]);
            }
            else return edgeObject;
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
     * Colors an array of node paths
     * @param {array} data array of arrays
     * @param {boolean} visualization. If true: opacity to 0.1, false: 0.0 (hidden)
     * @example colorPaths([[1,34,5,56],[123,234,3,4]], false)
     */
    function colorPaths(data, visualization) {

        /**
         * Returns a random integer between min (inclusive) and max (inclusive)
         * Using Math.round() will give you a non-uniform distribution!
         */
        function getRandomInt(min, max) {
            return Math.floor(Math.random() * (max - min + 1)) + min;
        }

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
            " #990014", " #d97b6c", " #ff8800", " #f2ffbf", " #e5c339", " #5ba629", " #005947", " #005580", " #090040",
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

        nodeNames.push(value.cname);

        $("#node-list-ul").append("<li class='list-group-item'><input class='node-checkbox' type='checkbox'>" +
            "<div class='circle " + value.function + "'>" +
            "</div><span class='node-" + value.id + "'>" + value.cname + "</span></li>");
    });

    var duplicates = findDuplicates(nodeNames);

    var nodeNamesToId = {};

    // Check over duplicate cnames and create hashmap to id
    $.each(graph.nodes, function (key, value) {
        // if the node has no duplicate show it in autocompletion with its cname
        if (duplicates.indexOf(value.cname) < 0) {
            nodeNamesToId[value.cname] = value.id;
        }
        // if it has a duplicate show also the function after the cname
        else {
            nodeNamesToId[value.cname + ' (' + value.function + ')'] = value.id;
        }
    });

    var checkNodes = $("#get-checked-nodes");

    checkNodes.off('click'); // It will unbind the previous click if multiple graphs has been rendered

    // Highlight only selected nodes in the graph
    checkNodes.on("click", function (event) {
        event.preventDefault();
        var checkedItems = [];
        $(".node-checkbox:checked").each(function (idx, li) {
            // Get the class of the span element (node-ID) Strips "node-" and evaluate the string to integer
            checkedItems.push(parseInt(li.parentElement.childNodes[2].className.replace("node-", "")));
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


    $.each(graph.links, function (key, value) {

        $("#edge-list-ul").append("<li class='list-group-item'><input class='edge-checkbox' type='checkbox'><span>" +
            value.source.cname + ' ' + value.relation + ' ' + value.target.cname + "</span></li>");

    });

    var checkNodesButton = $("#get-checked-edges");

    checkNodesButton.off('click'); // It will unbind the previous click if multiple graphs has been rendered

    checkNodesButton.on("click", function (event) {
        event.preventDefault();

        var checkedItems = [];
        $(".edge-checkbox:checked").each(function (idx, li) {
            checkedItems.push(li.parentElement.childNodes[1].innerHTML);
        });

        resetAttributes();

        highlightEdges(checkedItems, 'cname');

        resetAttributesDoubleClick()
    });

    var pathForm = $("#path-form");

    var pathButton = $("#button-paths");

    pathButton.off('click'); // It will unbind the previous click if multiple graphs has been rendered

    pathButton.on("click", function () {
        if (pathForm.valid()) {

            var checkbox = pathForm.find("input[name='visualization-options']").is(":checked");

            args["source"] = nodeNamesToId[pathForm.find("input[name='source']").val()];
            args["target"] = nodeNamesToId[pathForm.find("input[name='target']").val()];
            args["paths_method"] = $("input[name=paths_method]:checked", pathForm).val();

            var undirected = pathForm.find("input[name='undirectionalize']").is(":checked");

            if (undirected) {
                args["undirected"] = undirected;
            }

            $.ajax({
                url: "/api/network/query/" + window.query + "paths/",
                type: pathForm.attr("method"),
                dataType: "json",
                data: $.param(args, true),
                success: function (paths) {

                    if (args["paths_method"] === "all") {
                        if (paths.length === 0) {
                            alert("No paths between the selected nodes");
                        }

                        resetAttributes();

                        // Apply changes in style for select paths
                        hideNodesTextInPaths(paths, checkbox, 'id');
                        colorPaths(paths, checkbox);
                        resetAttributesDoubleClick()
                    }
                    else {

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
                }, error: function (request) {
                    alert(request.responseText);
                }
            })
        }
    });

    // Path validation form
    pathForm.validate(
        {
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


    // Get or show all paths between two nodes via Ajax

    var betwennessForm = $("#betweenness-centrality");

    var betweennessButton = $("#betweenness-button");

    betweennessButton.off('click'); // It will unbind the previous click if multiple graphs has been rendered

    betweennessButton.on("click", function () {
        if (betwennessForm.valid()) {

            args["node_number"] = betwennessForm.find("input[name='betweenness']").val();

            $.ajax({
                url: "/api/network/query/" + window.query + "centrality/",
                type: betwennessForm.attr("method"),
                dataType: "json",
                data: $.param(args, true),
                success: function (data) {

                    var nodesToIncrease = nodesInArrayKeepOrder(data, 'id');

                    var nodesToReduce = nodesNotInArray(data, 'id');

                    // Reduce to 7 radius the nodes not in top x
                    $.each(nodesToReduce._groups[0], function (index, value) {
                        value.childNodes[0].setAttribute("r", "7");
                    });

                    // Make bigger by factor scale the nodes in the top x
                    //TODO: change this coefficient
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

    betwennessForm.validate(
        {
            rules: {
                betweenness: {
                    required: true,
                    digits: true
                }
            },
            messages: {
                betweenness: "Please enter a number"
            }
        }
    );


    // Get normalized results from NPA analysis given an experiment ID

    var npaForm = $("#npa-form");

    var npaButton = $("#npa-button");

    betweennessButton.off('click'); // It will unbind the previous click if multiple graphs has been rendered

    npaButton.on("click", function () {
        if (npaForm.valid()) {

            var experimentID = $("#analysis_id").val();

            $.ajax({
                url: "/api/network/query/" + window.query + "analysis/" + experimentID + "/median",
                type: npaForm.attr("method"),
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

                    var mappedNodes = nodesInArrayKeepOrder(nodeIDStrings.map(Number), 'id');

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

    npaForm.validate(
        {
            rules: {
                analysis_id: {
                    required: true,
                    digits: true
                }
            },
            messages: {
                analysis_id: "Please enter a number corresponding to the ID of an experiment"
            }
        }
    );

    var hideNodeNames = $("#hide_node_names");

    hideNodeNames.off('click'); // It will unbind the previous click if multiple graphs has been rendered

    // Hide text in graph
    hideNodeNames.on("click", function () {
        svg.selectAll(".node-name").style("display", "none");
    });

    var restoreNodeNames = $("#restore_node_names");

    restoreNodeNames.off('click'); // It will unbind the previous click if multiple graphs has been rendered

    // Hide text in graph
    restoreNodeNames.on("click", function () {
        svg.selectAll(".node-name").style("display", "block");
    });

    var restoreAll = $("#restore");

    restoreAll.off('click'); // It will unbind the previous click if multiple graphs has been rendered

    // Restore all
    restoreAll.on("click", function () {
        resetAttributes();
    });

    var removeNodeHighlighting = $("#remove-node-highlighting");

    removeNodeHighlighting.off('click'); // It will unbind the previous click if multiple graphs has been rendered

    // Restore all
    removeNodeHighlighting.on("click", function () {
        removeHighlightNodeBorder();
    });
}

