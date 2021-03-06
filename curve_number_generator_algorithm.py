# -*- coding: utf-8 -*-

"""
/***************************************************************************
 CurveNumberGenerator
                                 A QGIS plugin
 This plugin generates a Curve Number layer for the given Area of Interest within the contiguous United States. It can also download Soil and Land Cover datasets for the same area.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2020-06-06
        copyright            : (C) 2020 by Abdul Raheem Siddiqui
        email                : mailto:ars.work.ce@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import sys
import inspect
import requests
import os
import processing
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing,
    QgsFeatureSink,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFeatureSource,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterDefinition,
    QgsCoordinateReferenceSystem,
    QgsExpression,
    QgsVectorLayer,
    QgsDistanceArea,
    QgsUnitTypes,
    QgsCoordinateTransformContext,
    QgsProject,
    QgsGeometry,
    QgsField,
    QgsFeature,
)

cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
sys.path.append(cmd_folder)

from cust_functions import check_crs_acceptable

__author__ = "Abdul Raheem Siddiqui"
__date__ = "2020-12-25"
__copyright__ = "(C) 2020 by Abdul Raheem Siddiqui"

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = "$Format:%H$"


class CurveNumberGeneratorAlgorithm(QgsProcessingAlgorithm):

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

    OUTPUT = "OUTPUT"
    INPUT = "INPUT"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                "areaboundary",
                "Area Boundary",
                types=[QgsProcessing.TypeVectorPolygon],
                defaultValue=None,
            )
        )
        param = QgsProcessingParameterFeatureSource(
            "cnlookup",
            "CN_Lookup.csv",
            optional=True,
            types=[QgsProcessing.TypeVector],
            defaultValue="",
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        param = QgsProcessingParameterBoolean(
            "drainedsoilsleaveuncheckedifnotsure",
            "Drained Soils? [leave unchecked if not sure]",
            defaultValue=False,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)
        self.addParameter(
            QgsProcessingParameterBoolean(
                "OutputNLCDLandCoverRaster",
                "Output NLCD Land Cover Raster",
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                "OutputNLCDLandCoverVector",
                "Output NLCD Land Cover Vector",
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                "OutputSoilLayer", "Output Soil Layer", defaultValue=False
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                "OutputCurveNumberLayer",
                "Output Curve Number Layer",
                defaultValue=False,
            )
        )

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(21, model_feedback)
        results = {}
        outputs = {}

        nlcd_rast_output = self.parameterAsBool(
            parameters, "OutputNLCDLandCoverRaster", context
        )
        nlcd_vect_output = self.parameterAsBool(
            parameters, "OutputNLCDLandCoverVector", context
        )
        soil_output = self.parameterAsBool(parameters, "OutputSoilLayer", context)
        curve_number_output = self.parameterAsBool(
            parameters, "OutputCurveNumberLayer", context
        )

        # Assiging Default CN_Lookup Table
        if parameters["cnlookup"] == None:
            csv_uri = (
                "file:///" + os.path.join(cmd_folder, "CN_Lookup.csv") + "?delimiter=,"
            )
            csv = QgsVectorLayer(csv_uri, "CN_Lookup.csv", "delimitedtext")
            parameters["cnlookup"] = csv
            # feedback.pushInfo(str(csv_uri))

        area_layer = self.parameterAsVectorLayer(parameters, "areaboundary", context)
        EPSGCode = area_layer.crs().authid()
        if check_crs_acceptable(EPSGCode):
            pass
        else:
            # Reproject layer to EPSG:5070
            alg_params = {
                "INPUT": parameters["areaboundary"],
                "OPERATION": "",
                "TARGET_CRS": QgsCoordinateReferenceSystem("EPSG:5070"),
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["ReprojectLayer5070"] = processing.run(
                "native:reprojectlayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )
            area_layer = context.takeResultLayer(
                outputs["ReprojectLayer5070"]["OUTPUT"]
            )
            EPSGCode = area_layer.crs().authid()

        # Check if area of the extent is less than 100,000 Acres
        d = QgsDistanceArea()
        tr_cont = QgsCoordinateTransformContext()
        d.setSourceCrs(area_layer.crs(), tr_cont)
        # d.setEllipsoid(area_layer.crs().ellipsoidAcronym())
        extent_area = d.measureArea(QgsGeometry().fromRect(area_layer.extent()))
        area_acres = d.convertAreaMeasurement(extent_area, QgsUnitTypes.AreaAcres)

        if area_acres < 100000:
            feedback.pushInfo(
                str(
                    "Area Boundary layer extent area is "
                    + str(area_acres)
                    + " acres"
                    + "\n"
                )
            )
        else:
            feedback.reportError(
                "Area Boundary layer extent area should be less than 100,000 acres"
                + "\n"
                + "\n"
                + "Execution Failed",
                True,
            )
            return results

        # NLCD Data

        if (
            curve_number_output == True
            or nlcd_vect_output == True
            or nlcd_rast_output == True
        ):
            # Get extent of the area boundary layer
            xmin = area_layer.extent().xMinimum()
            ymin = area_layer.extent().yMinimum()
            xmax = area_layer.extent().xMaximum()
            ymax = area_layer.extent().yMaximum()

            BBOX_width = (xmax - xmin) / 30
            BBOX_height = (ymax - ymin) / 30
            BBOX_width_int = round(BBOX_width)
            BBOX_height_int = round(BBOX_height)
            request_URL = (
                "https://www.mrlc.gov/geoserver/mrlc_display/NLCD_2016_Land_Cover_L48/ows?version=1.3.0&service=WMS&layers=NLCD_2016_Land_Cover_L48&styles&crs="
                + str(EPSGCode)
                + "&format=image/geotiff&request=GetMap&width="
                + str(BBOX_width_int)
                + "&height="
                + str(BBOX_height_int)
                + "&BBOX="
                + str(xmin)
                + ","
                + str(ymin)
                + ","
                + str(xmax)
                + ","
                + str(ymax)
                + "&"
            )
            # feedback.pushInfo(request_URL)

            # Download NLCD
            alg_params = {"URL": request_URL, "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT}
            outputs["DownloadNlcd"] = processing.run(
                "native:filedownloader",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(1)
            if feedback.isCanceled():
                return {}

            # Reclassify by table
            alg_params = {
                "DATA_TYPE": 5,
                "INPUT_RASTER": outputs["DownloadNlcd"]["OUTPUT"],
                "NODATA_FOR_MISSING": False,
                "NO_DATA": -9999,
                "RANGE_BOUNDARIES": 0,
                "RASTER_BAND": 1,
                "TABLE": QgsExpression(
                    "'0,1,11,1,2,12,2,3,21,3,4,22,4,5,23,5,6,24,6,7,31,7,8,32,8,9,41,9,10,42,10,11,43,11,12,51,12,13,52,13,14,71,14,15,72,15,16,73,16,17,74,17,18,81,18,19,82,19,20,90,20,21,95'"
                ).evaluate(),
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["ReclassifyByTable"] = processing.run(
                "native:reclassifybytable",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(2)
            if feedback.isCanceled():
                return {}

            # Set layer style
            alg_params = {
                "INPUT": outputs["ReclassifyByTable"]["OUTPUT"],
                "STYLE": os.path.join(cmd_folder, "NLCD_Raster.qml"),
            }

            try:  # for QGIS Version later than 3.12
                outputs["SetLayerStyle"] = processing.run(
                    "native:setlayerstyle",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )
            except:  # for QGIS Version older than 3.12
                outputs["SetStyleForRasterLayer"] = processing.run(
                    "qgis:setstyleforrasterlayer",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )

            feedback.setCurrentStep(3)
            if feedback.isCanceled():
                return {}

            if curve_number_output == True or nlcd_vect_output == True:
                # Polygonize (raster to vector)
                alg_params = {
                    "BAND": 1,
                    "EIGHT_CONNECTEDNESS": False,
                    "EXTRA": "",
                    "FIELD": "VALUE",
                    "INPUT": outputs["ReclassifyByTable"]["OUTPUT"],
                    "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                }
                outputs["PolygonizeRasterToVector"] = processing.run(
                    "gdal:polygonize",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )

                feedback.setCurrentStep(4)
                if feedback.isCanceled():
                    return {}

                # Fix geometries
                alg_params = {
                    "INPUT": outputs["PolygonizeRasterToVector"]["OUTPUT"],
                    "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                }
                outputs["FixGeometries"] = processing.run(
                    "native:fixgeometries",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )

                feedback.setCurrentStep(5)
                if feedback.isCanceled():
                    return {}

                # Set layer style
                alg_params = {
                    "INPUT": outputs["FixGeometries"]["OUTPUT"],
                    "STYLE": os.path.join(cmd_folder, "NLCD_Vector.qml"),
                }
                try:  # for QGIS Version 3.12 and later
                    outputs["SetLayerStyle"] = processing.run(
                        "native:setlayerstyle",
                        alg_params,
                        context=context,
                        feedback=feedback,
                        is_child_algorithm=True,
                    )
                except:  # for QGIS Version older than 3.12
                    outputs["SetStyleForVectorLayer"] = processing.run(
                        "qgis:setstyleforvectorlayer",
                        alg_params,
                        context=context,
                        feedback=feedback,
                        is_child_algorithm=True,
                    )

                feedback.setCurrentStep(6)
                if feedback.isCanceled():
                    return {}

        # Soil Layer

        if soil_output == True or curve_number_output == True:

            # Reproject layer
            alg_params = {
                "INPUT": parameters["areaboundary"],
                "OPERATION": "",
                "TARGET_CRS": QgsCoordinateReferenceSystem("EPSG:4326"),
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["ReprojectLayer4326"] = processing.run(
                "native:reprojectlayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(7)
            if feedback.isCanceled():
                return {}

            # Get Area Boundary layer extent in EPSG:4326
            area_layer_reprojected = context.takeResultLayer(
                outputs["ReprojectLayer4326"]["OUTPUT"]
            )

            # Download Soil

            try:  # request using post rest

                # create vector layer structure to store data
                feedback.pushInfo("post")
                uri = "Polygon?crs=epsg:4326"
                soil_layer = QgsVectorLayer(uri, "soil layer", "memory")
                provider = soil_layer.dataProvider()
                attributes = []
                attr_dict = [
                    {"name": "musym", "type": "str"},
                    {"name": "muname", "type": "str"},
                    {"name": "mustatus", "type": "str"},
                    {"name": "slopegraddcp", "type": "str"},
                    {"name": "slopegradwta", "type": "str"},
                    {"name": "brockdepmin", "type": "str"},
                    {"name": "wtdepannmin", "type": "str"},
                    {"name": "wtdepaprjunmin", "type": "str"},
                    {"name": "flodfreqdcd", "type": "str"},
                    {"name": "flodfreqmax", "type": "str"},
                    {"name": "pondfreqprs", "type": "str"},
                    {"name": "aws025wta", "type": "str"},
                    {"name": "aws050wta", "type": "str"},
                    {"name": "aws0100wta", "type": "str"},
                    {"name": "aws0150wta", "type": "str"},
                    {"name": "drclassdcd", "type": "str"},
                    {"name": "drclasswettest", "type": "str"},
                    {"name": "hydgrpdcd", "type": "str"},
                    {"name": "iccdcd", "type": "str"},
                    {"name": "iccdcdpct", "type": "str"},
                    {"name": "niccdcd", "type": "str"},
                    {"name": "niccdcdpct", "type": "str"},
                    {"name": "engdwobdcd", "type": "str"},
                    {"name": "engdwbdcd", "type": "str"},
                    {"name": "engdwbll", "type": "str"},
                    {"name": "engdwbml", "type": "str"},
                    {"name": "engstafdcd", "type": "str"},
                    {"name": "engstafll", "type": "str"},
                    {"name": "engstafml", "type": "str"},
                    {"name": "engsldcd", "type": "str"},
                    {"name": "engsldcp", "type": "str"},
                    {"name": "englrsdcd", "type": "str"},
                    {"name": "engcmssdcd", "type": "str"},
                    {"name": "engcmssmp", "type": "str"},
                    {"name": "urbrecptdcd", "type": "str"},
                    {"name": "urbrecptwta", "type": "str"},
                    {"name": "forpehrtdcp", "type": "str"},
                    {"name": "hydclprs", "type": "str"},
                    {"name": "awmmfpwwta", "type": "str"},
                    {"name": "mukey", "type": "str"},
                    {"name": "mupolygonkey", "type": "str"},
                    {"name": "areasymbol", "type": "str"},
                    {"name": "nationalmusym", "type": "str"},
                ]

                # initialize fields
                for field in attr_dict:
                    attributes.append(QgsField(field["name"], QVariant.String))
                    provider.addAttributes(attributes)
                    soil_layer.updateFields()

                # get area layer extent polygon as WKT in 4326
                aoi_reproj_wkt = area_layer_reprojected.extent().asWktPolygon()

                # send post request
                body = {
                    "format": "JSON",
                    "query": f"select Ma.*, M.mupolygonkey, M.areasymbol, M.nationalmusym, M.mupolygongeo from mupolygon M, muaggatt Ma where M.mupolygonkey in (select * from SDA_Get_Mupolygonkey_from_intersection_with_WktWgs84('{aoi_reproj_wkt.lower()}')) and M.mukey=Ma.mukey",
                }
                url = "https://sdmdataaccess.sc.egov.usda.gov/TABULAR/post.rest"
                soil_response = requests.post(url, json=body).json()

                feedback.setCurrentStep(8)
                if feedback.isCanceled():
                    return {}

                for row in soil_response["Table"]:
                    # None attribute for empty data
                    row = [None if not attr else attr for attr in row]
                    feat = QgsFeature(soil_layer.fields())
                    # populate data
                    for index, col in enumerate(row):
                        if index != len(attr_dict):
                            feat.setAttribute(attr_dict[index]["name"], col)
                        else:
                            feat.setGeometry(QgsGeometry.fromWkt(col))
                    provider.addFeatures([feat])

                feedback.setCurrentStep(9)
                if feedback.isCanceled():
                    return {}

            except:  # try wfs request

                xmin_reprojected = area_layer_reprojected.extent().xMinimum()
                ymin_reprojected = area_layer_reprojected.extent().yMinimum()
                xmax_reprojected = area_layer_reprojected.extent().xMaximum()
                ymax_reprojected = area_layer_reprojected.extent().yMaximum()

                request_URL_soil = (
                    "https://sdmdataaccess.sc.egov.usda.gov/Spatial/SDMWGS84GEOGRAPHIC.wfs?SERVICE=WFS&VERSION=1.1.0&REQUEST=GetFeature&TYPENAME=mapunitpolyextended&SRSNAME=EPSG:4326&BBOX="
                    + str(xmin_reprojected)
                    + ","
                    + str(ymin_reprojected)
                    + ","
                    + str(xmax_reprojected)
                    + ","
                    + str(ymax_reprojected)
                )

                alg_params = {
                    "URL": request_URL_soil,
                    "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                }
                outputs["DownloadSoil"] = processing.run(
                    "native:filedownloader",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )

                feedback.setCurrentStep(8)
                if feedback.isCanceled():
                    return {}

                # Swap X and Y coordinates
                alg_params = {
                    "INPUT": outputs["DownloadSoil"]["OUTPUT"],
                    "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                }
                outputs["SwapXAndYCoordinates"] = processing.run(
                    "native:swapxy",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )

                feedback.setCurrentStep(9)
                if feedback.isCanceled():
                    return {}

                soil_layer = outputs["SwapXAndYCoordinates"]["OUTPUT"]

            # Fix soil layer geometries
            alg_params = {"INPUT": soil_layer, "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT}
            outputs["FixGeometries2"] = processing.run(
                "native:fixgeometries",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(10)
            if feedback.isCanceled():
                return {}

            # Clip Soil Layer
            alg_params = {
                "INPUT": outputs["FixGeometries2"]["OUTPUT"],
                "OVERLAY": parameters["areaboundary"],
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["Clip"] = processing.run(
                "native:clip",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(11)
            if feedback.isCanceled():
                return {}

            # Reproject Soil
            alg_params = {
                "INPUT": outputs["Clip"]["OUTPUT"],
                "OPERATION": "",
                "TARGET_CRS": QgsCoordinateReferenceSystem(EPSGCode),
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["ReprojectSoil"] = processing.run(
                "native:reprojectlayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(12)
            if feedback.isCanceled():
                return {}

            # Set layer style
            alg_params = {
                "INPUT": outputs["ReprojectSoil"]["OUTPUT"],
                "STYLE": os.path.join(cmd_folder, "Soil_Layer.qml"),
            }
            try:  # for QGIS Version 3.12 and later
                outputs["SetLayerStyle"] = processing.run(
                    "native:setlayerstyle",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )
            except:  # for QGIS Version older than 3.12
                outputs["SetStyleForVectorLayer"] = processing.run(
                    "qgis:setstyleforvectorlayer",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )

            feedback.setCurrentStep(13)
            if feedback.isCanceled():
                return {}

        # Curve Number Calculations

        if curve_number_output == True:

            # Intersection
            alg_params = {
                "INPUT": outputs["ReprojectSoil"]["OUTPUT"],
                "INPUT_FIELDS": ["MUSYM", "HYDGRPDCD", "MUNAME"],
                "OVERLAY": outputs["FixGeometries"]["OUTPUT"],
                "OVERLAY_FIELDS": ["VALUE"],
                "OVERLAY_FIELDS_PREFIX": "",
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["Intersection"] = processing.run(
                "native:intersection",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(14)
            if feedback.isCanceled():
                return {}

            # Create GDCodeTemp
            alg_params = {
                "FIELD_LENGTH": 5,
                "FIELD_NAME": "GDCodeTemp",
                "FIELD_PRECISION": 3,
                "FIELD_TYPE": 2,
                "FORMULA": 'IF ("HYDGRPDCD" IS NOT NULL, "Value" || "HYDGRPDCD", IF (("MUSYM" = \'W\' OR lower("MUSYM") = \'water\' OR lower("MUNAME") = \'water\' OR "MUNAME" = \'W\'), 11, "VALUE"))',
                "INPUT": outputs["Intersection"]["OUTPUT"],
                "NEW_FIELD": True,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["CreateGdcodetemp"] = processing.run(
                "qgis:fieldcalculator",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(15)
            if feedback.isCanceled():
                return {}

            # Create GDCode
            alg_params = {
                "FIELD_LENGTH": 5,
                "FIELD_NAME": "GDCode",
                "FIELD_PRECISION": 3,
                "FIELD_TYPE": 2,
                "FORMULA": "if( var('drainedsoilsleaveuncheckedifnotsure') = True,replace(\"GDCodeTemp\", '/D', ''),replace(\"GDCodeTemp\", map('A/', '', 'B/', '', 'C/', '')))",
                "INPUT": outputs["CreateGdcodetemp"]["OUTPUT"],
                "NEW_FIELD": True,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["CreateGdcode"] = processing.run(
                "qgis:fieldcalculator",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(16)
            if feedback.isCanceled():
                return {}

            # Create NLCD_LU
            alg_params = {
                "FIELD_LENGTH": 2,
                "FIELD_NAME": "NLCD_LU",
                "FIELD_PRECISION": 3,
                "FIELD_TYPE": 1,
                "FORMULA": '"Value"',
                "INPUT": outputs["CreateGdcode"]["OUTPUT"],
                "NEW_FIELD": True,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["CreateNlcd_lu"] = processing.run(
                "qgis:fieldcalculator",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(17)
            if feedback.isCanceled():
                return {}

            # Join with CNLookup
            alg_params = {
                "DISCARD_NONMATCHING": False,
                "FIELD": "GDCode",
                "FIELDS_TO_COPY": ["CN_Join"],
                "FIELD_2": "GDCode",
                "INPUT": outputs["CreateNlcd_lu"]["OUTPUT"],
                "INPUT_2": parameters["cnlookup"],
                "METHOD": 1,
                "PREFIX": "",
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["JoinWithCnlookup"] = processing.run(
                "native:joinattributestable",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(18)
            if feedback.isCanceled():
                return {}

            # Create Integer CN
            alg_params = {
                "FIELD_LENGTH": 3,
                "FIELD_NAME": "CN",
                "FIELD_PRECISION": 0,
                "FIELD_TYPE": 1,
                "FORMULA": "CN_Join  * 1",
                "INPUT": outputs["JoinWithCnlookup"]["OUTPUT"],
                "NEW_FIELD": True,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["CreateIntegerCn"] = processing.run(
                "qgis:fieldcalculator",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(19)
            if feedback.isCanceled():
                return {}

            # Drop field(s)
            alg_params = {
                "COLUMN": ["VALUE", "GDCodeTemp", "CN_Join"],
                "INPUT": outputs["CreateIntegerCn"]["OUTPUT"],
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
            }
            outputs["DropFields"] = processing.run(
                "qgis:deletecolumn",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

            feedback.setCurrentStep(20)
            if feedback.isCanceled():
                return {}

            # Set layer style
            alg_params = {
                "INPUT": outputs["DropFields"]["OUTPUT"],
                "STYLE": os.path.join(cmd_folder, "CN_Grid.qml"),
            }
            try:  # for QGIS Version 3.12 and later
                outputs["SetLayerStyle"] = processing.run(
                    "native:setlayerstyle",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )
            except:  # for QGIS Version older than 3.12
                outputs["SetStyleForVectorLayer"] = processing.run(
                    "qgis:setstyleforvectorlayer",
                    alg_params,
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True,
                )

        if nlcd_rast_output:
            # Load NLCD Raster into project
            alg_params = {
                "INPUT": outputs["ReclassifyByTable"]["OUTPUT"],
                "NAME": "NLCD Land Cover Raster",
            }
            outputs["LoadLayerIntoProject1"] = processing.run(
                "native:loadlayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

        if nlcd_vect_output:
            # Load NLCD Vector Layer into project
            alg_params = {
                "INPUT": outputs["FixGeometries"]["OUTPUT"],
                "NAME": "NLCD Land Cover Vector",
            }
            outputs["LoadLayerIntoProject2"] = processing.run(
                "native:loadlayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

        if soil_output:
            # Load Soil Layer into project
            alg_params = {
                "INPUT": outputs["ReprojectSoil"]["OUTPUT"],
                "NAME": "SSURGO Soil Layer",
            }
            outputs["LoadLayerIntoProject3"] = processing.run(
                "native:loadlayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

        if curve_number_output:
            # Load Curve Number Layer into project
            alg_params = {
                "INPUT": outputs["DropFields"]["OUTPUT"],
                "NAME": "Curve Number Layer",
            }
            outputs["LoadLayerIntoProject4"] = processing.run(
                "native:loadlayer",
                alg_params,
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )

        return results

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return "Curve Number Generator"

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr(self.name())

    def group(self):
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr(self.groupId())

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return ""

    def tr(self, string):
        return QCoreApplication.translate("Processing", string)

    def icon(self):
        cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
        icon = QIcon(os.path.join(os.path.join(cmd_folder, "logo.png")))
        return icon

    def shortHelpString(self):
        return """<html><body><h2>Algorithm description</h2>
<p>This algorithm generates Curve Number layer for the given Area of Interest within the contiguous United States. It can also download Soil and Land Cover datasets for the same area.</p>
<h2>Input parameters</h2>
<h3>Area Boundary</h3>
<p>Area of Interest</p>
<h3>CN_Lookup.csv [optional]</h3>
<p>Optional Table to relate NLCD Land Use Value and HSG Value to a particular curve number. By default the algorithm uses pre defined table. The table must have two columns 'GDCode' and 'CN_Join'. GDCode is concatenation of NLCD Land Use code and Hydrologic Soil Group. <a href="https://drive.google.com/file/d/1NwFzP8mBObrxkzt_QZCdeAQXQPQQENUZ/view">Template to create custom table.</a></p>
<h3>Drained Soils? [leave unchecked if not sure]</h3>
<p>Certain Soils are categorized as dual category in SSURGO dataset. They have Hydrologic Soil Group D for Undrained Conditions and Hydrologic Soil Group A/B/C for Drained Conditions.

If left unchecked, the algorithm will assume HSG D for all dual category soils. 

If checked the algorithm will assume HSG A/B/C for each dual category soil.</p>
<h2>Outputs</h2>
<h3>NLCD Land Cover Vector</h3>
<p>NLCD 2016 Land Cover Dataset Vectorized</p>
<h3>NLCD Land Cover Raster</h3>
<p>NLCD 2016 Land Cover Dataset</p>
<h3>Soil Layer</h3>
<p>SSURGO Extended Soil Dataset </p>
<h3>Curve Number Layer</h3>
<p>Generated Curve Number Layer based on Land Cover and HSG values.</p>
<br><p align="right">Algorithm author: Abdul Raheem Siddiqui</p><p align="right">Help author: Abdul Raheem Siddiqui</p><p align="right">Algorithm version: 1.0</p><p align="right">Contact email: ars.work.ce@gmail.com</p><p>Disclaimer: The curve numbers generated with this algorithm are high level estimates and should be reviewed in detail before being used for detailed modeling or construction projects.</p></body></html>"""

    def helpUrl(self):
        return "mailto:ars.work.ce@gmail.com"

    def createInstance(self):
        return CurveNumberGeneratorAlgorithm()
